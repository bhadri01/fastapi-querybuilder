#!/usr/bin/env python3
"""Quick test to verify the demo fix"""
import sys
sys.path.insert(0, '/workspaces/fastapi-querybuilder')

from examples.main import demo_sql_generation

try:
    demo_sql_generation()
    print("\n✅ Demo SQL generation completed successfully!")
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
