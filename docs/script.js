// ===========================
// Theme Management
// ===========================

function initTheme() {
  const themeToggle = document.querySelector('.theme-toggle');
  const html = document.documentElement;
  const prismDark = document.getElementById('prism-dark');
  const prismLight = document.getElementById('prism-light');
  
  // Get saved theme or default to light
  const savedTheme = localStorage.getItem('theme') || 'light';
  html.setAttribute('data-theme', savedTheme);
  updatePrismTheme(savedTheme);
  
  themeToggle.addEventListener('click', () => {
    const currentTheme = html.getAttribute('data-theme');
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
    
    html.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    updatePrismTheme(newTheme);
  });
  
  function updatePrismTheme(theme) {
    if (theme === 'dark') {
      prismDark.disabled = false;
      prismLight.disabled = true;
    } else {
      prismDark.disabled = true;
      prismLight.disabled = false;
    }
  }
}

// ===========================
// Mobile Menu
// ===========================

function initMobileMenu() {
  const menuBtn = document.querySelector('.mobile-menu-btn');
  const sidebar = document.querySelector('.sidebar');
  
  menuBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    menuBtn.classList.toggle('active');
    sidebar.classList.toggle('open');
  });
  
  // Close sidebar when clicking outside
  document.addEventListener('click', (e) => {
    if (!sidebar.contains(e.target) && !menuBtn.contains(e.target)) {
      menuBtn.classList.remove('active');
      sidebar.classList.remove('open');
    }
  });
  
  // Close sidebar when clicking a link on mobile
  const sidebarLinks = sidebar.querySelectorAll('a');
  sidebarLinks.forEach(link => {
    link.addEventListener('click', () => {
      if (window.innerWidth <= 1024) {
        menuBtn.classList.remove('active');
        sidebar.classList.remove('open');
      }
    });
  });
}

// ===========================
// Smooth Scrolling
// ===========================

function initSmoothScroll() {
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
      const href = this.getAttribute('href');
      if (href === '#' || href === '') return;
      
      e.preventDefault();
      const target = document.querySelector(href);
      
      if (target) {
        const headerHeight = document.querySelector('.header').offsetHeight;
        const targetPosition = target.offsetTop - headerHeight - 20;
        
        window.scrollTo({
          top: targetPosition,
          behavior: 'smooth'
        });
      }
    });
  });
}

// ===========================
// Active Section Highlighting
// ===========================

function initSectionObserver() {
  const sections = document.querySelectorAll('section[id], .subsection[id]');
  const navLinks = document.querySelectorAll('.sidebar-nav a');
  
  const observerOptions = {
    root: null,
    rootMargin: '-20% 0px -70% 0px',
    threshold: 0
  };
  
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        // Remove active class from all links
        navLinks.forEach(link => link.classList.remove('active'));
        
        // Add active class to current section link
        const id = entry.target.getAttribute('id');
        const activeLink = document.querySelector(`.sidebar-nav a[href="#${id}"]`);
        if (activeLink) {
          activeLink.classList.add('active');
        }
      }
    });
  }, observerOptions);
  
  sections.forEach(section => observer.observe(section));
}

// ===========================
// Code Copy Functionality
// ===========================

function copyCode(button) {
  const codeBlock = button.closest('.code-block');
  const code = codeBlock.querySelector('code');
  const text = code.textContent;
  
  navigator.clipboard.writeText(text).then(() => {
    // Update button state
    const originalHTML = button.innerHTML;
    button.innerHTML = '<i class="fas fa-check"></i><span>Copied!</span>';
    button.classList.add('copied');
    
    // Reset after 2 seconds
    setTimeout(() => {
      button.innerHTML = originalHTML;
      button.classList.remove('copied');
    }, 2000);
  }).catch(err => {
    console.error('Failed to copy code:', err);
    button.innerHTML = '<i class="fas fa-times"></i><span>Failed</span>';
    setTimeout(() => {
      button.innerHTML = '<i class="fas fa-copy"></i><span>Copy</span>';
    }, 2000);
  });
}

// ===========================
// Back to Top Button
// ===========================

function initBackToTop() {
  const backToTopBtn = document.querySelector('.back-to-top');
  
  window.addEventListener('scroll', () => {
    if (window.scrollY > 500) {
      backToTopBtn.classList.add('visible');
    } else {
      backToTopBtn.classList.remove('visible');
    }
  });
  
  backToTopBtn.addEventListener('click', () => {
    window.scrollTo({
      top: 0,
      behavior: 'smooth'
    });
  });
}

// ===========================
// Search Functionality
// ===========================

function initSearch() {
  const searchInput = document.getElementById('search-input');
  const navSections = document.querySelectorAll('.nav-section');
  
  searchInput.addEventListener('input', (e) => {
    const query = e.target.value.toLowerCase().trim();
    
    navSections.forEach(section => {
      const links = section.querySelectorAll('li');
      let hasVisibleLinks = false;
      
      links.forEach(link => {
        const text = link.textContent.toLowerCase();
        const isMatch = text.includes(query);
        
        link.style.display = isMatch || !query ? 'block' : 'none';
        
        if (isMatch || !query) {
          hasVisibleLinks = true;
        }
      });
      
      // Hide section if no visible links
      section.style.display = hasVisibleLinks || !query ? 'block' : 'none';
    });
  });
  
  // Clear search on Escape key
  searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      searchInput.value = '';
      searchInput.dispatchEvent(new Event('input'));
      searchInput.blur();
    }
  });
}

// ===========================
// External Links
// ===========================

function initExternalLinks() {
  const links = document.querySelectorAll('a[href^="http"]');
  
  links.forEach(link => {
    if (!link.hostname.includes(window.location.hostname)) {
      link.setAttribute('target', '_blank');
      link.setAttribute('rel', 'noopener noreferrer');
    }
  });
}

// ===========================
// Keyboard Navigation
// ===========================

function initKeyboardNav() {
  document.addEventListener('keydown', (e) => {
    // Toggle theme with Ctrl/Cmd + K
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      document.querySelector('.theme-toggle').click();
    }
    
    // Focus search with Ctrl/Cmd + F or /
    if (((e.ctrlKey || e.metaKey) && e.key === 'f') || e.key === '/') {
      const searchInput = document.getElementById('search-input');
      if (document.activeElement !== searchInput) {
        e.preventDefault();
        searchInput.focus();
        searchInput.select();
      }
    }
  });
}

// ===========================
// Loading Animation
// ===========================

function initLoadingAnimation() {
  document.addEventListener('DOMContentLoaded', () => {
    document.body.classList.add('loaded');
  });
}

// ===========================
// Scroll Progress Bar
// ===========================

function initScrollProgress() {
  const progressBar = document.createElement('div');
  progressBar.className = 'scroll-progress';
  progressBar.style.cssText = `
    position: fixed;
    top: var(--header-height);
    left: 0;
    width: 0%;
    height: 3px;
    background: linear-gradient(90deg, var(--color-primary), var(--color-accent));
    z-index: 1001;
    transition: width 0.1s ease;
  `;
  document.body.appendChild(progressBar);
  
  window.addEventListener('scroll', () => {
    const scrollTop = window.pageYOffset;
    const docHeight = document.documentElement.scrollHeight - window.innerHeight;
    const scrollPercent = (scrollTop / docHeight) * 100;
    progressBar.style.width = scrollPercent + '%';
  });
}

// ===========================
// Code Block Enhancements
// ===========================

function enhanceCodeBlocks() {
  const codeBlocks = document.querySelectorAll('.code-block');
  
  codeBlocks.forEach(block => {
    const pre = block.querySelector('pre');
    const code = pre.querySelector('code');
    
    // Add line numbers for longer code blocks
    if (code.textContent.split('\n').length > 5) {
      pre.classList.add('line-numbers');
    }
    
    // Add hover effect
    block.addEventListener('mouseenter', () => {
      const copyBtn = block.querySelector('.copy-btn');
      if (copyBtn) {
        copyBtn.style.opacity = '1';
      }
    });
    
    block.addEventListener('mouseleave', () => {
      const copyBtn = block.querySelector('.copy-btn');
      if (copyBtn && !copyBtn.classList.contains('copied')) {
        copyBtn.style.opacity = '0.7';
      }
    });
  });
}

// ===========================
// Header Scroll Effect
// ===========================

function initHeaderScroll() {
  const header = document.querySelector('.header');
  let lastScroll = 0;
  
  window.addEventListener('scroll', () => {
    const currentScroll = window.pageYOffset;
    
    if (currentScroll > 100) {
      header.style.boxShadow = 'var(--shadow-md)';
    } else {
      header.style.boxShadow = 'none';
    }
    
    // Optional: Hide header on scroll down, show on scroll up
    // if (currentScroll > lastScroll && currentScroll > 200) {
    //   header.style.transform = 'translateY(-100%)';
    // } else {
    //   header.style.transform = 'translateY(0)';
    // }
    
    lastScroll = currentScroll;
  });
}

// ===========================
// Lazy Loading Images
// ===========================

function initLazyLoading() {
  const images = document.querySelectorAll('img[data-src]');
  
  const imageObserver = new IntersectionObserver((entries, observer) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const img = entry.target;
        img.src = img.dataset.src;
        img.removeAttribute('data-src');
        observer.unobserve(img);
      }
    });
  });
  
  images.forEach(img => imageObserver.observe(img));
}

// ===========================
// Tooltip Functionality
// ===========================

function initTooltips() {
  const elements = document.querySelectorAll('[data-tooltip]');
  
  elements.forEach(element => {
    element.addEventListener('mouseenter', (e) => {
      const tooltip = document.createElement('div');
      tooltip.className = 'tooltip';
      tooltip.textContent = element.dataset.tooltip;
      tooltip.style.cssText = `
        position: absolute;
        background: var(--color-text);
        color: var(--color-bg);
        padding: 0.5rem 0.75rem;
        border-radius: 0.375rem;
        font-size: 0.875rem;
        white-space: nowrap;
        z-index: 10000;
        pointer-events: none;
        box-shadow: var(--shadow-lg);
      `;
      document.body.appendChild(tooltip);
      
      const rect = element.getBoundingClientRect();
      tooltip.style.top = rect.top - tooltip.offsetHeight - 8 + 'px';
      tooltip.style.left = rect.left + (rect.width / 2) - (tooltip.offsetWidth / 2) + 'px';
      
      element._tooltip = tooltip;
    });
    
    element.addEventListener('mouseleave', () => {
      if (element._tooltip) {
        element._tooltip.remove();
        delete element._tooltip;
      }
    });
  });
}

// ===========================
// Analytics (Optional)
// ===========================

function initAnalytics() {
  // Track page views
  const trackPageView = () => {
    console.log('Page viewed:', window.location.href);
    // Add your analytics code here (Google Analytics, Plausible, etc.)
  };
  
  // Track outbound links
  document.querySelectorAll('a[href^="http"]').forEach(link => {
    link.addEventListener('click', () => {
      console.log('Outbound link clicked:', link.href);
      // Add your analytics code here
    });
  });
  
  // Track code copy events
  document.addEventListener('click', (e) => {
    if (e.target.closest('.copy-btn')) {
      console.log('Code copied');
      // Add your analytics code here
    }
  });
  
  trackPageView();
}

// ===========================
// Performance Monitoring
// ===========================

function monitorPerformance() {
  if ('performance' in window) {
    window.addEventListener('load', () => {
      const perfData = performance.getEntriesByType('navigation')[0];
      console.log('Page load time:', perfData.loadEventEnd - perfData.fetchStart, 'ms');
    });
  }
}

// ===========================
// Initialization
// ===========================

document.addEventListener('DOMContentLoaded', () => {
  // Core functionality
  initTheme();
  initMobileMenu();
  initSmoothScroll();
  initSectionObserver();
  initBackToTop();
  initSearch();
  
  // Enhancements
  initExternalLinks();
  initKeyboardNav();
  initScrollProgress();
  enhanceCodeBlocks();
  initHeaderScroll();
  initLazyLoading();
  initTooltips();
  
  // Optional
  // initAnalytics();
  // monitorPerformance();
  
  // Prism syntax highlighting
  if (typeof Prism !== 'undefined') {
    Prism.highlightAll();
  }
});

// ===========================
// Service Worker (Optional PWA)
// ===========================

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    // Uncomment to enable PWA
    // navigator.serviceWorker.register('/sw.js')
    //   .then(reg => console.log('Service Worker registered'))
    //   .catch(err => console.log('Service Worker registration failed:', err));
  });
}

// ===========================
// Export for external use
// ===========================

window.FastAPIQueryBuilderDocs = {
  copyCode,
  initTheme,
  initSearch
};
