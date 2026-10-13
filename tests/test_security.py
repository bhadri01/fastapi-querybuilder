"""Security regressions exercised against real SQLAlchemy mappings and SQLite.

The cardinality checks deliberately do not call Result.unique(): pagination and
counts must be correct in SQL, before any result-side ORM deduplication.
"""

import json
from datetime import datetime

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from fastapi_pagination import Page, Params, set_page
from fastapi_pagination.ext.sqlalchemy import paginate
from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, create_engine, func, select
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, synonym

import fastapi_querybuilder as qb
from fastapi_querybuilder.core import parse_filter_query


class Base(DeclarativeBase):
    pass


class Address(Base):
    __tablename__ = "security_addresses"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)


class Root(Base):
    __tablename__ = "security_roots"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    secret: Mapped[str] = mapped_column(String)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[str | None] = mapped_column(String, nullable=True)
    left_id: Mapped[int | None] = mapped_column(ForeignKey(Address.id), nullable=True)
    right_id: Mapped[int | None] = mapped_column(ForeignKey(Address.id), nullable=True)
    left: Mapped[Address | None] = relationship(foreign_keys=[left_id])
    right: Mapped[Address | None] = relationship(foreign_keys=[right_id])
    children: Mapped[list["Child"]] = relationship(back_populates="root")

    plain_attribute = "not a mapped column"


class Child(Base):
    __tablename__ = "security_children"

    id: Mapped[int] = mapped_column(primary_key=True)
    root_id: Mapped[int] = mapped_column(ForeignKey(Root.id))
    label: Mapped[str] = mapped_column(String)
    rank: Mapped[int] = mapped_column(Integer)
    root: Mapped[Root] = relationship(back_populates="children")
    notes: Mapped[list["Note"]] = relationship()


class Note(Base):
    __tablename__ = "security_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    child_id: Mapped[int] = mapped_column(ForeignKey(Child.id))
    text: Mapped[str] = mapped_column(String)


class NaturalRoot(Base):
    __tablename__ = "security_natural_roots"

    key: Mapped[str] = mapped_column("external_key", primary_key=True)
    name: Mapped[str] = mapped_column("stored_name", String)
    children: Mapped[list["NaturalChild"]] = relationship()


class NaturalChild(Base):
    __tablename__ = "security_natural_children"

    id: Mapped[int] = mapped_column(primary_key=True)
    root_key: Mapped[str] = mapped_column(ForeignKey(NaturalRoot.key))
    label: Mapped[str] = mapped_column(String)
    rank: Mapped[int] = mapped_column(Integer)


class CompositeRoot(Base):
    __tablename__ = "security_composite_roots"

    tenant: Mapped[str] = mapped_column(primary_key=True)
    key: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    children: Mapped[list["CompositeChild"]] = relationship()


class CompositeChild(Base):
    __tablename__ = "security_composite_children"
    __table_args__ = (
        ForeignKeyConstraint(
            ["root_tenant", "root_key"],
            ["security_composite_roots.tenant", "security_composite_roots.key"],
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    root_tenant: Mapped[str] = mapped_column(String)
    root_key: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String)
    rank: Mapped[int] = mapped_column(Integer)


class SynonymRoot(Base):
    __tablename__ = "security_synonym_roots"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String)
    name = synonym("title")
    removed_at: Mapped[str | None] = mapped_column(String, nullable=True)
    deleted_at = synonym("removed_at")
    children: Mapped[list["SynonymChild"]] = relationship()
    kids = synonym("children")


class SynonymChild(Base):
    __tablename__ = "security_synonym_children"

    id: Mapped[int] = mapped_column(primary_key=True)
    root_id: Mapped[int] = mapped_column(ForeignKey(SynonymRoot.id))
    label: Mapped[str] = mapped_column(String)


class HybridRoot(Base):
    __tablename__ = "security_hybrid_roots"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    removed_at: Mapped[str | None] = mapped_column(String, nullable=True)

    @hybrid_property
    def deleted_at(self):
        return self.removed_at


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        north = Address(name="north")
        south = Address(name="south")
        session.add_all(
            [
                Root(
                    id=1,
                    name="alpha",
                    secret="needle",
                    left=north,
                    right=south,
                    children=[
                        Child(label="red", rank=1, notes=[Note(text="memo")]),
                        Child(label="blue", rank=2),
                        Child(label="red", rank=3),
                    ],
                ),
                Root(
                    id=2,
                    name="needle",
                    secret="private",
                    left=south,
                    right=north,
                    children=[Child(label="red", rank=4), Child(label="blue", rank=5)],
                ),
                Root(id=3, name="gamma", secret="private"),
                Root(
                    id=4,
                    name="deleted",
                    secret="needle",
                    deleted_at="2026-01-01",
                    children=[Child(label="red", rank=0)],
                ),
                NaturalRoot(
                    key="a",
                    name="first",
                    children=[
                        NaturalChild(label="red", rank=1),
                        NaturalChild(label="red", rank=2),
                    ],
                ),
                NaturalRoot(
                    key="b",
                    name="second",
                    children=[NaturalChild(label="red", rank=3)],
                ),
                SynonymRoot(
                    id=1, title="alive",
                    children=[SynonymChild(label="red"), SynonymChild(label="red")],
                ),
                SynonymRoot(
                    id=2, title="deleted", removed_at="2026-01-01",
                    children=[SynonymChild(label="red")],
                ),
                HybridRoot(id=1, name="alive"),
                HybridRoot(id=2, name="deleted", removed_at="2026-01-01"),
            ]
        )
        for rank, (tenant, key) in enumerate([("a", 1), ("a", 2), ("b", 1)]):
            session.add(
                CompositeRoot(
                    tenant=tenant,
                    key=key,
                    name=f"{tenant}-{key}",
                    children=[
                        CompositeChild(label="red", rank=rank * 2),
                        CompositeChild(label="red", rank=rank * 2 + 1),
                    ],
                )
            )
        session.commit()
        yield session
    engine.dispose()


def params(**values):
    defaults = dict(filters=None, search=None, search_fields=None, sort=None, case_sensitive=False)
    defaults.update(values)
    if isinstance(defaults["filters"], dict):
        defaults["filters"] = json.dumps(defaults["filters"])
    return qb.QueryParams(**defaults)


def field_params(usage, path):
    if usage == "filter":
        return params(filters={path: {"$eq": "red"}})
    if usage == "search":
        return params(search="red", search_fields=path)
    return params(sort=path)


def assert_bad_request(callback):
    with pytest.raises(HTTPException) as error:
        callback()
    assert error.value.status_code == 400


@pytest.mark.parametrize("usage", ["filter", "search", "sort"])
@pytest.mark.parametrize(
    "path",
    [
        "__dict__",
        "__table__",
        "metadata",
        "plain_attribute",
        "name.unexpected_suffix",
        "children",
        "children.__dict__",
        "children.label.unexpected_suffix",
    ],
)
def test_rejects_unmapped_attributes_and_nonterminal_columns(usage, path):
    assert_bad_request(lambda: qb.build_query(Root, field_params(usage, path)))


@pytest.mark.parametrize("usage", ["filter", "search", "sort"])
def test_relationship_queries_deduplicate_before_limit_and_count(session, usage):
    query = qb.build_query(
        Root,
        field_params(usage, "children.rank" if usage == "sort" else "children.label"),
    )
    if usage == "sort":
        # Exclude the root without children so NULL ordering is not dialect-specific.
        query = query.where(Root.id < 3)
    else:
        query = query.order_by(Root.id)
    assert [row.id for row in session.scalars(query.limit(2)).all()] == [1, 2]
    assert session.scalar(select(func.count()).select_from(query.subquery())) == 2
    assert [row.id for row in session.scalars(query.offset(1).limit(1)).all()] == [2]


@pytest.mark.parametrize("usage", ["filter", "search", "sort"])
def test_fastapi_pagination_gets_full_pages_and_correct_totals(session, usage):
    query = qb.build_query(
        Root,
        field_params(usage, "children.rank" if usage == "sort" else "children.label"),
    ).where(Root.id < 3)
    if usage != "sort":
        query = query.order_by(Root.id)
    with set_page(Page[int]):
        first = paginate(
            session, query, Params(page=1, size=2),
            transformer=lambda rows: [row.id for row in rows], unique=False,
        )
        second = paginate(
            session, query, Params(page=2, size=1),
            transformer=lambda rows: [row.id for row in rows], unique=False,
        )
    assert first.items == [1, 2]
    assert first.total == 2
    assert first.pages == 1
    assert second.items == [2]
    assert second.total == 2
    assert second.pages == 2


@pytest.mark.parametrize("usage", ["filter", "search", "sort"])
@pytest.mark.parametrize("model", [NaturalRoot, CompositeRoot])
def test_deduplication_supports_non_id_and_composite_primary_keys(session, usage, model):
    query = qb.build_query(
        model,
        field_params(usage, "children.rank" if usage == "sort" else "children.label"),
    )
    if usage != "sort":
        query = query.order_by(*model.__mapper__.primary_key)
    rows = session.scalars(query.limit(2)).all()
    if model is NaturalRoot:
        assert [row.key for row in rows] == ["a", "b"]
        expected_count = 2
    else:
        assert [(row.tenant, row.key) for row in rows] == [("a", 1), ("a", 2)]
        expected_count = 3
    assert session.scalar(select(func.count()).select_from(query.subquery())) == expected_count


def test_and_branches_can_match_different_child_rows(session):
    query = qb.build_query(
        Root,
        params(
            filters={
                "$and": [
                    {"children.label": {"$eq": "red"}},
                    {"children.label": {"$eq": "blue"}},
                ]
            },
            sort="id",
        ),
    )
    assert [row.id for row in session.scalars(query).all()] == [1, 2]


def test_predicates_in_one_filter_dictionary_match_the_same_child(session):
    query = qb.build_query(
        Root,
        params(filters={"children.label": {"$eq": "red"}, "children.rank": {"$eq": 2}}),
    )
    assert session.scalars(query).all() == []


def test_independent_nested_branches_can_match_different_children(session):
    query = qb.build_query(
        Root,
        params(filters={"$and": [
            {"children.label": {"$eq": "blue"}},
            {"children.notes.text": {"$eq": "memo"}},
        ]}),
    )
    assert [row.id for row in session.scalars(query).all()] == [1]


@pytest.mark.parametrize("path,expected", [
    ("children.label", [3]),
    ("children.notes.text", [1, 2, 3]),
])
def test_isempty_preserves_missing_relationship_matches(session, path, expected):
    query = qb.build_query(Root, params(filters={path: {"$isempty": True}}, sort="id"))
    assert [row.id for row in session.scalars(query).all()] == expected


def test_nested_predicates_in_one_dictionary_use_the_same_child(session):
    query = qb.build_query(
        Root,
        params(filters={"children.label": {"$eq": "blue"}, "children.notes.text": {"$eq": "memo"}}),
    )
    assert session.scalars(query).all() == []


@pytest.mark.parametrize("operator", ["$in", "$isanyof"])
def test_empty_membership_lists_match_nothing(session, operator):
    query = qb.build_query(Root, params(filters={"id": {operator: []}}))
    assert session.scalars(query).all() == []


def test_different_relationships_to_same_model_keep_distinct_aliases(session):
    query = qb.build_query(
        Root,
        params(filters={"left.name": {"$eq": "north"}, "right.name": {"$eq": "south"}}),
    )
    assert [row.id for row in session.scalars(query).all()] == [1]


def test_or_search_keeps_roots_without_a_matching_relationship(session):
    query = qb.build_query(Root, params(search="gamma", search_fields="name,children.label"))
    assert [row.id for row in session.scalars(query).all()] == [3]


def test_explicit_search_without_a_type_compatible_expression_matches_nothing(session):
    query = qb.build_query(Root, params(search="not-an-integer", search_fields="id"))
    assert session.scalars(query).all() == []


def test_relationship_sort_descending_is_unique_before_limit(session):
    query = qb.build_query(Root, params(sort="children.rank:desc")).where(Root.id < 3)
    assert [row.id for row in session.scalars(query.limit(2)).all()] == [2, 1]


def test_relationship_sort_preserves_roots_without_children(session):
    query = qb.build_query(Root, params(sort="children.rank"))
    assert [row.id for row in session.scalars(query).all()] == [3, 1, 2]


def test_multiple_relationship_sorts_keep_distinct_paths(session):
    query = qb.build_query(Root, params(sort="right.name,left.name")).where(Root.id < 3)
    assert [row.id for row in session.scalars(query).all()] == [2, 1]


def test_multicolumn_relationship_sort_uses_one_lexicographic_child_row(session):
    session.add_all([
        Root(id=11, name="eleven", secret="private", children=[
            Child(label="a", rank=10), Child(label="z", rank=100),
        ]),
        Root(id=12, name="twelve", secret="private", children=[
            Child(label="a", rank=20), Child(label="z", rank=30),
        ]),
    ])
    session.commit()
    query = qb.build_query(Root, params(sort="children.label:asc,children.rank:desc")).where(Root.id > 10)
    assert [row.id for row in session.scalars(query.limit(2)).all()] == [12, 11]


def test_default_search_uses_mapped_attribute_names_instead_of_database_names(session):
    query = qb.build_query(
        NaturalRoot,
        params(search="first"),
        policy=qb.QueryPolicy(search_fields=frozenset({"name"})),
    )
    assert [row.key for row in session.scalars(query).all()] == ["a"]


@pytest.mark.parametrize("model", [SynonymRoot, HybridRoot])
def test_soft_delete_supports_server_owned_synonym_and_hybrid_expressions(session, model):
    query = qb.build_query(model, params())
    assert [row.id for row in session.scalars(query).all()] == [1]


@pytest.mark.parametrize("usage", ["filter", "search", "sort"])
def test_explicit_mapped_column_synonyms_remain_supported(session, usage):
    options = {
        "filter": params(filters={"name": {"$eq": "alive"}}),
        "search": params(search="alive", search_fields="name"),
        "sort": params(sort="name"),
    }
    query = qb.build_query(SynonymRoot, options[usage])
    assert [row.id for row in session.scalars(query).all()] == [1]


@pytest.mark.parametrize("usage", ["filter", "search", "sort"])
def test_relationship_synonyms_preserve_policy_and_deduplication(session, usage):
    query = qb.build_query(
        SynonymRoot,
        field_params(usage, "kids.label"),
        policy=qb.QueryPolicy(
            filter_fields=frozenset({"kids.label"}),
            search_fields=frozenset({"kids.label"}),
            sort_fields=frozenset({"kids.label"}),
            relationships=frozenset({"kids"}),
        ),
    )
    assert [row.id for row in session.scalars(query).all()] == [1]


def test_combined_filter_search_and_sort_remain_unique_and_keep_soft_delete(session):
    query = qb.build_query(
        Root,
        params(
            filters={"children.label": {"$eq": "red"}},
            search="blue",
            search_fields="children.label",
            sort="children.rank",
        ),
    )
    assert [row.id for row in session.scalars(query.limit(2)).all()] == [1, 2]
    assert session.scalar(select(func.count()).select_from(query.subquery())) == 2


def test_top_level_or_can_match_a_root_with_no_children(session):
    query = qb.build_query(
        Root,
        params(filters={"$or": [{"children.label": {"$eq": "red"}}, {"name": {"$eq": "gamma"}}]}),
    )
    assert [row.id for row in session.scalars(query.order_by(Root.id)).all()] == [1, 2, 3]


def test_limit_defaults_are_public_and_finite():
    limits = qb.QueryLimits()
    assert limits.max_filter_bytes == 16_384
    assert limits.max_filter_depth == 8
    assert limits.max_predicates == 100
    assert limits.max_in_items == 100
    assert limits.max_relationship_depth == 4
    assert limits.max_joins == 8
    assert limits.max_search_length == 256
    assert limits.max_search_fields == 20
    assert limits.max_sort_fields == 10
    assert limits.max_field_length == 256


@pytest.mark.parametrize(
    ("limit", "value", "query_params"),
    [
        ("max_filter_bytes", 5, params(filters={"name": {"$eq": "alpha"}})),
        (
            "max_filter_depth",
            1,
            params(filters={"$and": [{"$or": [{"name": {"$eq": "alpha"}}]}]}),
        ),
        (
            "max_predicates",
            1,
            params(filters={"$or": [{"name": {"$eq": "alpha"}}, {"name": {"$eq": "needle"}}]}),
        ),
        ("max_in_items", 1, params(filters={"name": {"$in": ["alpha", "needle"]}})),
        ("max_in_items", 1, params(filters={"id": {"$isanyof": [1, 2]}})),
        ("max_relationship_depth", 1, params(filters={"children.notes.text": {"$eq": "memo"}})),
        ("max_relationship_depth", 1, params(search="memo", search_fields="children.notes.text")),
        ("max_relationship_depth", 1, params(sort="children.notes.text")),
        ("max_search_length", 3, params(search="four")),
        ("max_search_fields", 1, params(search="needle", search_fields="name,secret")),
        ("max_sort_fields", 1, params(sort="name,id")),
        ("max_field_length", 4, params(filters={"secret": {"$eq": "needle"}})),
        ("max_field_length", 4, params(search="needle", search_fields="secret")),
        ("max_field_length", 4, params(sort="secret")),
    ],
)
def test_individual_query_limits_are_enforced(limit, value, query_params):
    assert_bad_request(
        lambda: qb.build_query(Root, query_params, limits=qb.QueryLimits(**{limit: value}))
    )


def test_filter_size_budget_counts_utf8_bytes():
    raw = json.dumps({"name": {"$eq": "é"}}, ensure_ascii=False)
    assert len(raw.encode("utf-8")) > len(raw)
    assert_bad_request(
        lambda: qb.build_query(Root, params(filters=raw), limits=qb.QueryLimits(max_filter_bytes=len(raw)))
    )


def test_query_exactly_at_each_applicable_budget_is_accepted(session):
    raw = json.dumps({"name": {"$in": ["alpha"]}})
    query = qb.build_query(
        Root,
        params(filters=raw, search="alpha", search_fields="name", sort="name"),
        limits=qb.QueryLimits(
            max_filter_bytes=len(raw.encode("utf-8")),
            max_filter_depth=1,
            max_predicates=1,
            max_in_items=1,
            max_relationship_depth=0,
            max_joins=0,
            max_search_length=5,
            max_search_fields=1,
            max_sort_fields=1,
            max_field_length=4,
        ),
    )
    assert [row.id for row in session.scalars(query).all()] == [1]


def test_filter_depth_boundary_accepts_one_logical_group(session):
    query = qb.build_query(
        Root,
        params(filters={"$and": [{"name": {"$eq": "alpha"}}]}),
        limits=qb.QueryLimits(max_filter_depth=2, max_predicates=1),
    )
    assert [row.id for row in session.scalars(query).all()] == [1]


def test_relationship_depth_and_join_boundaries_are_inclusive(session):
    query = qb.build_query(
        Root,
        params(filters={"children.notes.text": {"$eq": "memo"}}),
        limits=qb.QueryLimits(max_relationship_depth=2, max_joins=2),
    )
    assert [row.id for row in session.scalars(query).all()] == [1]


@pytest.mark.parametrize("usage", ["filter", "search", "sort"])
def test_repeated_path_in_one_scope_reuses_its_join_budget(session, usage):
    options = {
        "filter": params(filters={"children.label": {"$eq": "red"}, "children.rank": {"$gte": 1}}),
        "search": params(search="red", search_fields="children.label,children.rank"),
        "sort": params(sort="children.label,children.rank"),
    }
    query = qb.build_query(Root, options[usage], limits=qb.QueryLimits(max_joins=1)).where(Root.id < 3)
    assert sorted(row.id for row in session.scalars(query).all()) == [1, 2]


def test_join_budget_is_shared_across_filter_search_and_sort():
    assert_bad_request(
        lambda: qb.build_query(
            Root,
            params(
                filters={"children.label": {"$eq": "red"}},
                search="north",
                search_fields="left.name",
                sort="right.name",
            ),
            limits=qb.QueryLimits(max_joins=2),
        )
    )


def test_join_budget_counts_independent_filter_branches():
    assert_bad_request(
        lambda: qb.build_query(
            Root,
            params(filters={"$and": [{"children.label": {"$eq": "red"}}, {"children.label": {"$eq": "blue"}}]}),
            limits=qb.QueryLimits(max_joins=1),
        )
    )


@pytest.mark.parametrize("operand", ["red", 1, {"unexpected": "red"}, [["red"]], [None, {"x": 1}]])
@pytest.mark.parametrize("operator", ["$in", "$isanyof"])
def test_membership_operators_reject_non_scalar_list_operands(operator, operand):
    assert_bad_request(lambda: qb.build_query(Root, params(filters={"name": {operator: operand}})))


@pytest.mark.parametrize("value", [-(2**63) - 1, 2**63, 10**100])
@pytest.mark.parametrize("operator", ["$eq", "$in", "$isanyof"])
def test_oversized_integer_operands_are_rejected_before_database_execution(operator, value):
    operand = [1, value] if operator in {"$in", "$isanyof"} else value
    assert_bad_request(lambda: qb.build_query(Root, params(filters={"id": {operator: operand}})))


def test_signed_64_bit_integer_boundary_values_execute_safely(session):
    query = qb.build_query(Root, params(filters={"id": {"$in": [-(2**63), 1, 2**63 - 1]}}))
    assert [row.id for row in session.scalars(query).all()] == [1]


@pytest.mark.parametrize("value", ["9" * 100, str(2**63), "²"])
@pytest.mark.parametrize("explicit", [False, True])
def test_huge_or_nonascii_numeric_search_terms_execute_safely(session, value, explicit):
    query = qb.build_query(Root, params(search=value, search_fields="id" if explicit else None))
    assert session.scalars(query).all() == []


@pytest.mark.parametrize("operator", ["$eq", "$ne", "$gt", "$lte"])
def test_date_max_range_overflow_is_reported_as_400(operator):
    assert_bad_request(
        lambda: qb.build_query(Root, params(filters={"occurred_at": {operator: "9999-12-31"}}))
    )


@pytest.mark.parametrize("operator", ["$gt", "$gte", "$lt", "$lte"])
def test_ordered_comparison_with_null_is_reported_as_400(operator):
    assert_bad_request(lambda: qb.build_query(Root, params(filters={"id": {operator: None}})))


@pytest.mark.parametrize("query_params", [
    params(filters='{"name":{"$eq":"\\ud800"}}'),
    params(filters='{"name":{"$in":["\\udfff"]}}'),
    params(filters='{"name":{"$eq":"\ud800"}}'),
    params(search="\ud800"),
    params(search="alpha", search_fields="name\ud800"),
    params(sort="name\ud800"),
])
def test_lone_surrogates_are_rejected_before_database_execution(query_params):
    assert_bad_request(lambda: qb.build_query(Root, query_params))


@pytest.mark.parametrize("raw", [
    '[]', 'null', 'false', '"text"', '{"name":NaN}',
    '{"name":{"$eq":Infinity}}', '{"name":{"$eq":1e10000}}',
])
def test_invalid_json_shapes_and_nonfinite_values_are_rejected(raw):
    assert_bad_request(lambda: qb.build_query(Root, params(filters=raw)))


@pytest.mark.parametrize("raw", [
    "{" * 17_000,
    "[" * 2_000 + "0" + "]" * 2_000,
    '{"$and":[' * 200 + '{}' + ']}' * 200,
    '{"name":{"$eq":"' + "x" * 17_000,
])
def test_huge_and_deep_malformed_json_fails_with_400(raw):
    assert_bad_request(lambda: qb.build_query(Root, params(filters=raw)))


def test_filter_nesting_scanner_ignores_braces_and_escaped_quotes_in_strings(session):
    raw = json.dumps({"name": {"$eq": '[{"escaped": "\\\""}]' * 50}})
    query = qb.build_query(Root, params(filters=raw), limits=qb.QueryLimits(max_filter_depth=1))
    assert session.scalars(query).all() == []


def test_parsed_filter_results_cannot_mutate_later_queries(session):
    raw = json.dumps({"name": {"$eq": "alpha"}})
    parsed = parse_filter_query(raw)
    parsed["name"]["$eq"] = "needle"
    query = qb.build_query(Root, params(filters=raw))
    assert [row.id for row in session.scalars(query).all()] == [1]


@pytest.mark.parametrize("usage", ["filter", "search", "sort"])
def test_per_usage_field_allowlists_are_enforced(usage):
    key = {"filter": "filter_fields", "search": "search_fields", "sort": "sort_fields"}[usage]
    policy = qb.QueryPolicy(**{key: frozenset({"name"})})
    assert_bad_request(lambda: qb.build_query(Root, field_params(usage, "secret"), policy=policy))


@pytest.mark.parametrize("usage", ["filter", "search", "sort"])
def test_empty_relationship_allowlist_blocks_relationship_traversal(usage):
    assert_bad_request(
        lambda: qb.build_query(
            Root,
            field_params(usage, "children.label"),
            policy=qb.QueryPolicy(relationships=frozenset()),
        )
    )


@pytest.mark.parametrize("allowed", [frozenset({"children"}), frozenset({"children.notes"})])
def test_relationship_allowlist_checks_every_path_prefix(allowed):
    assert_bad_request(
        lambda: qb.build_query(
            Root,
            params(filters={"children.notes.text": {"$eq": "memo"}}),
            policy=qb.QueryPolicy(relationships=allowed),
        )
    )


def test_allowed_nested_paths_work_with_explicit_policy(session):
    query = qb.build_query(
        Root,
        params(filters={"children.notes.text": {"$eq": "memo"}}),
        policy=qb.QueryPolicy(
            filter_fields=frozenset({"children.notes.text"}),
            relationships=frozenset({"children", "children.notes"}),
        ),
    )
    assert [row.id for row in session.scalars(query).all()] == [1]


def test_sort_double_underscore_notation_uses_canonical_policy_path(session):
    query = qb.build_query(
        Root,
        params(sort="children__rank"),
        policy=qb.QueryPolicy(sort_fields=frozenset({"children.rank"}), relationships=frozenset({"children"})),
    ).where(Root.id < 3)
    assert [row.id for row in session.scalars(query).all()] == [1, 2]


def test_default_search_only_uses_allowed_columns(session):
    query = qb.build_query(
        Root,
        params(search="needle"),
        policy=qb.QueryPolicy(search_fields=frozenset({"name"})),
    )
    assert [row.id for row in session.scalars(query).all()] == [2]


@pytest.mark.parametrize("allowed", [frozenset(), frozenset({"id"}), frozenset({"children.label"})])
def test_default_search_with_no_eligible_expression_never_returns_all_rows(session, allowed):
    query = qb.build_query(Root, params(search="needle"), policy=qb.QueryPolicy(search_fields=allowed))
    assert session.scalars(query).all() == []


def test_policy_is_per_query_and_does_not_contaminate_default_metadata_cache(session):
    restricted = qb.build_query(Root, params(search="needle"), policy=qb.QueryPolicy(search_fields=frozenset({"name"})))
    unrestricted = qb.build_query(Root, params(search="needle"))
    assert [row.id for row in session.scalars(restricted).all()] == [2]
    assert [row.id for row in session.scalars(unrestricted.order_by(Root.id)).all()] == [1, 2]


@pytest.mark.parametrize("usage", ["filter", "search"])
def test_user_values_remain_bound_parameters(session, usage):
    payload = "' OR 1=1; DROP TABLE security_roots; --"
    query_params = (
        params(filters={"name": {"$eq": payload}})
        if usage == "filter"
        else params(search=payload, search_fields="name")
    )
    query = qb.build_query(Root, query_params)
    assert payload not in str(query.compile())
    assert session.scalars(query).all() == []
    assert session.scalar(select(func.count()).select_from(Root)) == 4


def test_querybuilder_dependency_forwards_limits_and_policy():
    app = FastAPI()

    @app.get("/roots")
    def roots(query=qb.QueryBuilder(
        Root,
        limits=qb.QueryLimits(max_search_length=3),
        policy=qb.QueryPolicy(sort_fields=frozenset({"name"})),
    )):
        return {"query": str(query)}

    with TestClient(app) as client:
        assert client.get("/roots", params={"search": "four"}).status_code == 400
        assert client.get("/roots", params={"sort": "secret"}).status_code == 400
        assert client.get("/roots", params={"search": "four", "max_search_length": 100}).status_code == 400
        assert client.get("/roots", params={"sort": "secret", "sort_fields": "secret"}).status_code == 400
        assert client.get("/roots", params={"sort": "name"}).status_code == 200


@pytest.mark.parametrize("usage", ["filter", "search", "sort"])
def test_invalid_attribute_is_an_http_400_at_the_fastapi_boundary(usage):
    app = FastAPI()

    @app.get("/roots")
    def roots(query=qb.QueryBuilder(Root)):
        return {"query": str(query)}

    query_params = field_params(usage, "__dict__")
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/roots",
            params={key: value for key, value in vars(query_params).items() if value is not None},
        )
    assert response.status_code == 400


@pytest.mark.parametrize("term", ["0" * 100 + "1", "١"])
def test_zero_padded_and_unicode_decimal_searches_keep_numeric_semantics(session, term):
    query = qb.build_query(Root, params(search=term, search_fields="id"))
    assert [row.id for row in session.scalars(query).all()] == [1]


def test_default_search_policy_accepts_mapped_synonyms(session):
    query = qb.build_query(
        SynonymRoot, params(search="alive"),
        policy=qb.QueryPolicy(search_fields={"name"}),
    )
    assert [row.id for row in session.scalars(query).all()] == [1]
