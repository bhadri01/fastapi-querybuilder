document.addEventListener('DOMContentLoaded', () => {
    // Theme Toggle Logic
    const themeToggle = document.querySelector('.theme-toggle');
    const htmlElement = document.documentElement;
    const icon = themeToggle.querySelector('i');
    
    // Check saved theme
    const savedTheme = localStorage.getItem('theme') || 'dark';
    htmlElement.setAttribute('data-theme', savedTheme);
    updateThemeIcon(savedTheme);

    themeToggle.addEventListener('click', () => {
        const currentTheme = htmlElement.getAttribute('data-theme');
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        
        htmlElement.setAttribute('data-theme', newTheme);
        localStorage.setItem('theme', newTheme);
        updateThemeIcon(newTheme);
    });

    function updateThemeIcon(theme) {
        if (theme === 'dark') {
            themeToggle.innerHTML = '<i class="fas fa-sun"></i>';
        } else {
            themeToggle.innerHTML = '<i class="fas fa-moon"></i>';
        }
    }

    // Table of Contents Generation
    const tocContainer = document.querySelector('.right-sidebar');
    if (tocContainer) {
        const headings = document.querySelectorAll('main h2, main h3');
        const tocList = document.createElement('div');
        tocList.className = 'toc-nav';
        
        const tocTitle = document.createElement('div');
        tocTitle.className = 'toc-title';
        tocTitle.textContent = 'On this page';
        tocContainer.appendChild(tocTitle);

        headings.forEach((heading, index) => {
            const link = document.createElement('a');
            link.className = `toc-link ${heading.tagName.toLowerCase()}-link`;
            link.textContent = heading.textContent.trim();
            
            // Generate ID if missing
            if (!heading.id) {
                heading.id = `heading-${index}`;
            }
            
            link.href = `#${heading.id}`;
            
            link.addEventListener('click', (e) => {
                e.preventDefault();
                document.getElementById(heading.id).scrollIntoView({
                    behavior: 'smooth'
                });
                
                // Update active state
                document.querySelectorAll('.toc-link').forEach(l => l.classList.remove('active'));
                link.classList.add('active');
            });
            
            tocList.appendChild(link);
        });
        
        tocContainer.appendChild(tocList);

        // ScrollSpy for TOC
        const observerOptions = {
            root: null,
            rootMargin: '-100px 0px -66%',
            threshold: 0
        };

        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const id = entry.target.id;
                    document.querySelectorAll('.toc-link').forEach(link => {
                        link.classList.remove('active');
                        if (link.getAttribute('href') === `#${id}`) {
                            link.classList.add('active');
                        }
                    });
                }
            });
        }, observerOptions);

        headings.forEach(heading => observer.observe(heading));
    }

    // Copy Code Functionality
    document.querySelectorAll('.copy-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const codeBlock = btn.closest('.code-block');
            const code = codeBlock.querySelector('code').innerText;
            
            navigator.clipboard.writeText(code).then(() => {
                const originalText = btn.innerHTML;
                btn.innerHTML = '<i class="fas fa-check"></i> Copied!';
                btn.style.color = 'var(--accent-success)';
                
                setTimeout(() => {
                    btn.innerHTML = originalText;
                    btn.style.color = '';
                }, 2000);
            });
        });
    });

    // Mobile Menu
    const mobileMenuBtn = document.querySelector('.mobile-menu-btn');
    const sidebar = document.querySelector('.sidebar');
    
    if (mobileMenuBtn) {
        mobileMenuBtn.addEventListener('click', () => {
             // Simple toggle for mobile sidebar if we implemented a slide-out
             sidebar.classList.toggle('active');
        });
    }
});
