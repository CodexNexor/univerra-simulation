<template>
  <div class="landing-page" ref="landingEl">
    <!-- Top Navigation -->
    <nav class="landing-nav" :class="{ 'scrolled-nav': scrollY > 50 }">
      <div class="nav-left">UNIVERRA</div>
      <div class="nav-center">
        <a href="#home" class="nav-link">Home</a>
        <a href="#how-it-works" class="nav-link">How it Works</a>
        <a href="#pricing" class="nav-link">Pricing</a>
        <router-link to="/about" class="nav-link">About</router-link>
      </div>
      <div class="nav-right">
        <router-link to="/login" class="nav-link">Login</router-link>
        <router-link to="/signup" class="signup-btn">Sign Up</router-link>
      </div>
    </nav>

    <!-- Hero Section with sticky 3D scroll -->
    <section id="home" class="hero-scroll-track">
      <div class="hero-sticky-container">
        <!-- 3D Transform wrapper -->
        <div
          class="hero-3d-wrapper"
          :style="{
            transform: `perspective(1200px) rotateX(${scrollRotation}deg) scale(${scrollScale}) translateY(${scrollRotation * 2}px)`
          }"
        >
          <div class="hero-top-text">NAVIGATING THE UNKNOWN, PIXEL BY PIXEL.</div>
          <div class="drag-pill">SCROLL TO EXPLORE</div>

          <div class="hero-titles">
            <h1 class="title-solid">UNIVERRA</h1>
            <h1 class="title-outline">UNIVERRA</h1>
          </div>

          <div class="hero-bottom-text">Precision structure, bold creative vision.</div>

          <router-link to="/signup" class="get-started-btn">
            Get Started <span class="arrow">↗</span>
          </router-link>
        </div>
      </div>
    </section>

    <!-- SaaS Marketing Sections -->
    <div class="content-sections">

      <!-- How It Works Section -->
      <section id="how-it-works" class="saas-section">
        <div class="section-header">
          <span class="section-tag">Mechanism / Workflow</span>
          <h2 class="section-title">How the System Works</h2>
          <p class="section-desc">Deploy a parallel architecture to predict and map real-world public reactions.</p>
        </div>

        <div class="features-grid">
          <div class="feature-card">
            <div class="feature-icon">01</div>
            <h3>Inject Reality Seeds</h3>
            <p>Upload your proposal, text, or documentation into the swarm engine. Univerra automatically extracts critical entities and parameters to establish context.</p>
          </div>
          <div class="feature-card">
            <div class="feature-icon">02</div>
            <h3>Initialize Agent Personas</h3>
            <p>Thousands of unique simulated demographic personas are automatically constructed and mapped to GraphRAG memory paths based on sociological data.</p>
          </div>
          <div class="feature-card">
            <div class="feature-icon">03</div>
            <h3>Execute & Extract Forecasts</h3>
            <p>Observe the simulated world react dynamically to your proposal over defined rounds. Extract a definitive analysis report predicting sentiment and failure points.</p>
          </div>
        </div>
      </section>

      <!-- Pricing Plans Section -->
      <section id="pricing" class="saas-section">
        <div class="section-header">
          <span class="section-tag">Univerra Access</span>
          <h2 class="section-title">Transparent Pricing</h2>
          <p class="section-desc">Scale your simulation architecture as your organization's forecast demands grow.</p>
        </div>

        <div class="pricing-grid">
          <!-- Basic Plan -->
          <div class="pricing-card">
            <div class="plan-name">Researcher</div>
            <div class="plan-price">$49<span>/mo</span></div>
            <p class="plan-desc">For individuals and independent analysts predicting small-scale proposals.</p>
            <ul class="plan-features">
              <li>✓ Up to 100 simulated agents</li>
              <li>✓ 10 simulations per month</li>
              <li>✓ Base sociological demographics</li>
              <li>✓ Standard reporting</li>
            </ul>
            <router-link to="/signup" class="plan-btn">Start Free Trial</router-link>
          </div>

          <!-- Pro Plan -->
          <div class="pricing-card popular">
            <div class="popular-badge">Most Popular</div>
            <div class="plan-name">Enterprise Pro</div>
            <div class="plan-price">$299<span>/mo</span></div>
            <p class="plan-desc">For organizations relying on deep social mapping and risk forecasting.</p>
            <ul class="plan-features">
              <li>✓ Up to 10,000 simulated agents</li>
              <li>✓ Unlimited simulations</li>
              <li>✓ Advanced GraphRAG Memory</li>
              <li>✓ Premium predictive reports</li>
              <li>✓ Priority swarm computing speed</li>
            </ul>
            <router-link to="/signup" class="plan-btn primary">Upgrade to Pro</router-link>
          </div>
        </div>
      </section>

      <!-- Minimal Footer -->
      <footer class="minimal-footer">
        <div class="footer-left">© 2026 Univerra Simulation Engine.</div>
        <div class="footer-right">
          <router-link to="/terms">Terms</router-link>
          <router-link to="/about">Privacy</router-link>
        </div>
      </footer>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'

const scrollY = ref(0)
let scrollTimer = null

const handleScroll = () => {
  scrollY.value = window.scrollY
}

// 3D rotation logic only applies while scrolling through the hero track
const scrollRotation = computed(() => {
  // Cap rotation at 75 degrees
  const tilt = Math.min(scrollY.value * 0.15, 75)
  return tilt
})

const scrollScale = computed(() => {
  // Shrink as it tilts back to simulate distance
  return Math.max(1 - (scrollY.value * 0.001), 0.6)
})

onMounted(() => {
  window.addEventListener('scroll', handleScroll, { passive: true })
})

onUnmounted(() => {
  window.removeEventListener('scroll', handleScroll)
})
</script>

<style scoped>
.landing-page {
  /* Using standard scrolling */
  min-height: 100vh;
  background-color: #050505;
  color: #FAFAFA;
  font-family: var(--font-sans), 'Helvetica Neue', Arial, sans-serif;
}

/* Nav */
.landing-nav {
  position: fixed; /* Keep nav pinned to top */
  top: 0;
  left: 0;
  right: 0;
  padding: 24px 40px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-family: var(--font-mono), monospace;
  font-size: 11px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  z-index: 100;
  transition: background 0.3s, backdrop-filter 0.3s;
}

.scrolled-nav {
  background: rgba(5, 5, 5, 0.85);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  padding: 16px 40px;
}

.nav-center, .nav-right {
  display: flex;
  gap: 30px;
  align-items: center;
}

.nav-link {
  color: rgba(255, 255, 255, 0.6);
  text-decoration: none;
  transition: color 0.3s;
}

.nav-link:hover {
  color: #fff;
}

.signup-btn {
  background: #E8F5A2;
  color: #050505;
  text-decoration: none;
  padding: 8px 16px;
  border-radius: 4px;
  font-weight: 700;
  transition: transform 0.2s, background 0.2s;
}

.signup-btn:hover {
  background: #F4FAC8;
  transform: scale(1.05);
}

/* Hero Sticky Track */
.hero-scroll-track {
  /* We give this section extra height to scroll *through* it while the sticky container stays pinned */
  height: 150vh;
  position: relative;
  background-image: radial-gradient(rgba(255, 255, 255, 0.08) 1.5px, transparent 1.5px);
  background-size: 24px 24px;
}

.hero-sticky-container {
  position: sticky;
  top: 0;
  height: 100vh;
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  perspective: 1200px; /* 3D Perspective Origin */
  overflow: hidden;
}

/* 3D Wrapper */
.hero-3d-wrapper {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  transform-style: preserve-3d;
  will-change: transform;
  transform-origin: center center;
}

.hero-top-text {
  font-family: var(--font-mono), monospace;
  font-size: 11px;
  letter-spacing: 0.25em;
  color: rgba(255, 255, 255, 0.5);
  margin-bottom: 12px;
}

.drag-pill {
  background: #FFF;
  color: #000;
  font-family: var(--font-mono), monospace;
  font-size: 9px;
  font-weight: 700;
  padding: 4px 8px;
  border-radius: 4px;
  margin-bottom: 20px;
  letter-spacing: 0.1em;
}

.hero-titles {
  display: flex;
  flex-direction: column;
  align-items: center;
  line-height: 0.9;
  border: 1px dashed rgba(255, 255, 255, 0.2);
  padding: 20px 40px;
}

.title-solid {
  font-size: 14vw;
  font-weight: 800;
  margin: 0;
  color: #FFFFFF;
  letter-spacing: -0.02em;
}

.title-outline {
  font-size: 14vw;
  font-weight: 800;
  margin: 0;
  color: transparent;
  -webkit-text-stroke: 1px rgba(255, 255, 255, 0.6);
  letter-spacing: -0.02em;
}

.hero-bottom-text {
  font-size: 20px;
  font-weight: 300;
  color: rgba(255, 255, 255, 0.6);
  margin-top: 40px;
  letter-spacing: 0.01em;
}

.get-started-btn {
  margin-top: 40px;
  background: #E8F5A2;
  color: #050505;
  font-family: var(--font-mono), monospace;
  font-size: 14px;
  font-weight: 600;
  text-decoration: none;
  padding: 16px 32px;
  border-radius: 30px;
  display: flex;
  align-items: center;
  gap: 12px;
  transition: transform 0.3s, background 0.3s;
  box-shadow: 0 0 20px rgba(232, 245, 162, 0.2);
}

.get-started-btn:hover {
  transform: scale(1.05);
  background: #F4FAC8;
}

/* SaaS Content Sections flowing over the Hero */
.content-sections {
  position: relative;
  background: #050505; /* Solid background hides the hero when scrolled past */
  z-index: 10;
}

.saas-section {
  padding: 120px 40px;
  max-width: 1200px;
  margin: 0 auto;
}

.section-header {
  text-align: center;
  margin-bottom: 80px;
}

.section-tag {
  font-family: var(--font-mono), monospace;
  color: #E8F5A2;
  font-size: 12px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.section-title {
  font-size: 42px;
  font-weight: 600;
  margin: 16px 0;
}

.section-desc {
  font-size: 18px;
  color: rgba(255, 255, 255, 0.6);
  max-width: 500px;
  margin: 0 auto;
}

/* How It Works Grid */
.features-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 30px;
}

.feature-card {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
  padding: 40px;
  border-radius: 12px;
  transition: transform 0.3s, background 0.3s;
}

.feature-card:hover {
  transform: translateY(-8px);
  background: rgba(255, 255, 255, 0.05);
}

.feature-icon {
  font-family: var(--font-mono), monospace;
  font-size: 24px;
  color: #E8F5A2;
  margin-bottom: 24px;
}

.feature-card h3 {
  font-size: 20px;
  margin-bottom: 16px;
  font-weight: 500;
}

.feature-card p {
  color: rgba(255, 255, 255, 0.5);
  line-height: 1.6;
  font-size: 14px;
}

/* Pricing Grid */
.pricing-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  max-width: 800px;
  margin: 0 auto;
  gap: 30px;
}

.pricing-card {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
  padding: 40px;
  border-radius: 12px;
  position: relative;
}

.pricing-card.popular {
  background: rgba(232, 245, 162, 0.03);
  border: 1px solid rgba(232, 245, 162, 0.3);
}

.popular-badge {
  position: absolute;
  top: -12px;
  left: 50%;
  transform: translateX(-50%);
  background: #E8F5A2;
  color: #050505;
  font-family: var(--font-mono), monospace;
  font-size: 10px;
  padding: 4px 12px;
  border-radius: 12px;
  font-weight: 700;
  text-transform: uppercase;
}

.plan-name {
  font-size: 20px;
  font-weight: 500;
  margin-bottom: 12px;
}

.plan-price {
  font-size: 48px;
  font-weight: 700;
  margin-bottom: 24px;
}

.plan-price span {
  font-size: 16px;
  color: rgba(255, 255, 255, 0.4);
  font-weight: 400;
}

.plan-desc {
  color: rgba(255, 255, 255, 0.6);
  font-size: 14px;
  line-height: 1.5;
  margin-bottom: 30px;
  min-height: 42px;
}

.plan-features {
  list-style: none;
  padding: 0;
  margin-bottom: 40px;
}

.plan-features li {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.8);
  margin-bottom: 16px;
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.plan-btn {
  display: block;
  text-align: center;
  padding: 14px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.1);
  color: #FFF;
  text-decoration: none;
  font-weight: 600;
  transition: background 0.2s;
}

.plan-btn:hover {
  background: rgba(255, 255, 255, 0.2);
}

.plan-btn.primary {
  background: #FFF;
  color: #050505;
}

.plan-btn.primary:hover {
  background: #E8F5A2;
}

/* Footer */
.minimal-footer {
  border-top: 1px solid rgba(255, 255, 255, 0.05);
  padding: 40px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-family: var(--font-mono), monospace;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.4);
}

.footer-right {
  display: flex;
  gap: 20px;
}

.footer-right a {
  color: rgba(255, 255, 255, 0.4);
  text-decoration: none;
}

.footer-right a:hover {
  color: #FFF;
}

/* Responsiveness */
@media (max-width: 768px) {
  .title-solid, .title-outline {
    font-size: 18vw;
  }
  .landing-nav {
    flex-direction: column;
    gap: 15px;
    padding: 20px;
  }
  .features-grid, .pricing-grid {
    grid-template-columns: 1fr;
  }
  .hero-bottom-text {
    font-size: 16px;
  }
}
</style>
