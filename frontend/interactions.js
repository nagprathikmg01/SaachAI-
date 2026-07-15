/* ═══════════════════════════════════════════════════════════════════════════════
   SACHHAI INTERACTIVE SCRIPTS — Scroll Response & 3D Effects
   ═══════════════════════════════════════════════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', () => {
  const tabsContainer = document.querySelector('.floating-tabs-container');
  const tabItems = document.querySelectorAll('.floating-tab-item');
  const spySections = [
    { id: 'how-it-works', tabIndex: 0 },
    { id: 'features', tabIndex: 1 }
  ];

  // ── Enhanced Scroll Spy & Dynamic Highlighting ─────────────────────────────
  function updateActiveTab() {
    if (!tabsContainer) return;
    
    const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
    const scrollHeight = document.documentElement.scrollHeight;
    const clientHeight = document.documentElement.clientHeight;

    // 1. Sleek Show/Hide: Hide when reaching the footer/bottom area to avoid overlapping
    const isAtBottom = scrollTop + clientHeight >= scrollHeight - 120;
    if (isAtBottom) {
      tabsContainer.classList.add('tabs-hidden');
    } else {
      tabsContainer.classList.remove('tabs-hidden');
    }

    // 2. Translucent Glassmorphism background on scroll
    if (scrollTop > 100) {
      tabsContainer.classList.add('tabs-scrolled');
    } else {
      tabsContainer.classList.remove('tabs-scrolled');
    }

    // 3. Scroll Spy: Match currently viewed section
    let activeIndex = -1;
    spySections.forEach((sec, idx) => {
      const el = document.getElementById(sec.id);
      if (el) {
        const rect = el.getBoundingClientRect();
        // Section is considered active if it is positioned well in the viewport
        if (rect.top <= clientHeight * 0.45 && rect.bottom >= clientHeight * 0.2) {
          activeIndex = sec.tabIndex;
        }
      }
    });

    // Update the active state on tabs
    tabItems.forEach((tab, idx) => {
      if (idx === activeIndex) {
        tab.classList.add('active');
      } else {
        tab.classList.remove('active');
      }
    });
  }

  window.addEventListener('scroll', updateActiveTab, { passive: true });
  window.addEventListener('resize', updateActiveTab, { passive: true });
  setTimeout(updateActiveTab, 100);

  // ── Smooth Anchored Scrolling with Offset ──────────────────────────────────
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
      e.preventDefault();
      const targetId = this.getAttribute('href');
      if (targetId === '#') return;
      const targetEl = document.querySelector(targetId);
      if (targetEl) {
        const offsetTop = targetEl.offsetTop - 85; // Account for 70px sticky navbar + breathing room
        window.scrollTo({
          top: offsetTop,
          behavior: 'smooth'
        });
      }
    });
  });

  // ── 3D Tilt & Proximity Effect ───────────────────────────────────────────
  const cards = document.querySelectorAll('.card, .dash-card, .stat-card, .feature-card, .dash-glass-card');
  
  // Proximity detection for "Authenticity Score" and other widgets
  document.addEventListener('mousemove', (e) => {
    cards.forEach(card => {
      const rect = card.getBoundingClientRect();
      const cardCenterX = rect.left + rect.width / 2;
      const cardCenterY = rect.top + rect.height / 2;
      
      // Calculate distance from cursor to card center
      const deltaX = e.clientX - cardCenterX;
      const deltaY = e.clientY - cardCenterY;
      const distance = Math.sqrt(deltaX * deltaX + deltaY * deltaY);
      
      // Proximity threshold (e.g., 300px)
      const threshold = 300;
      
      if (distance < threshold) {
        // Calculate intensity based on distance (0 to 1)
        const intensity = 1 - (distance / threshold);
        
        // Apply subtle "magnetic" pull/tilt even before hover
        const tiltX = (deltaY / rect.height) * 15 * intensity;
        const tiltY = -(deltaX / rect.width) * 15 * intensity;
        const lift = intensity * 15;
        
        // Check if it's the Authenticity Score (contains "Authenticity Score" text)
        const isScoreCard = card.textContent.includes('Authenticity Score');
        const extraLift = isScoreCard ? (intensity * 10) : 0;
        
        card.style.transform = `perspective(1000px) translateY(${-lift - extraLift}px) rotateX(${tiltX}deg) rotateY(${tiltY}deg)`;
        card.style.boxShadow = `0 ${10 + lift}px ${20 + lift}px rgba(0, 0, 0, 0.4), 0 0 ${10 + lift}px rgba(0, 245, 255, ${0.1 + intensity * 0.2})`;
        
        if (isScoreCard) {
          card.classList.add('proximity-active');
        }
      } else {
        card.style.transform = '';
        card.style.boxShadow = '';
        card.classList.remove('proximity-active');
      }
    });
  });

  // ── Intersection Observer for Scroll Animations ────────────────────────────
  const observerOptions = {
    threshold: 0.05, // Trigger earlier
    rootMargin: '0px 0px 100px 0px' // Trigger before it enters the viewport
  };

  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        
        // Handle specific elements that need immediate reveal
        if (entry.target.classList.contains('reveal-item')) {
          entry.target.style.opacity = '1';
          entry.target.style.transform = 'translateY(0) scale(1)';
        }

        // If it's a stagger parent, trigger children
        if (entry.target.classList.contains('stagger-parent')) {
          const children = entry.target.querySelectorAll('.stagger-child');
          children.forEach((child, index) => {
            setTimeout(() => {
              child.classList.add('visible');
            }, index * 80); // Faster stagger
          });
        }
      }
    });
  }, observerOptions);

  // Observe all animatable elements (excl. reveal-item which is handled in landing.html)
  const animElements = document.querySelectorAll('.slide-left, .slide-right, .zoom-pop, .stagger-parent, .flip-in, .glow-appear, .animate-on-scroll, .fade-up, .dash-glass-card');
  animElements.forEach(el => {
    observer.observe(el);
  });

  // Force reveal elements already in viewport on load
  setTimeout(() => {
    animElements.forEach(el => {
      const rect = el.getBoundingClientRect();
      if (rect.top < window.innerHeight) {
        el.classList.add('visible');
      }
    });
  }, 100);
});
