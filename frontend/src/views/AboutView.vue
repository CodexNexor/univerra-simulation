<template>
  <div class="about-page">
    <nav class="landing-nav">
      <router-link to="/" class="nav-left nav-link">UNIVERRA</router-link>
      <div class="nav-right">
        <router-link to="/app" class="nav-link">WORK</router-link>
        <router-link to="/about" class="nav-link">ABOUT</router-link>
      </div>
    </nav>
    <div class="about-content">
      <h1 class="main-title cinematic-title">About Univerra</h1>
      <p class="hero-desc">
        Univerra is a predictive simulation platform that creates million-agent parallel worlds.
        It allows you to test variables, observe dynamic interactions, and forecast reality safely.
      </p>
      <div class="footer-links">
        <router-link to="/terms" class="footer-link">Terms & Conditions</router-link>
      </div>
    </div>
  </div>
</template>

<style scoped>
.about-page {
  min-height: 100vh;
  background-color: var(--bg-primary);
  color: var(--text-main);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
}
.landing-nav {
  position: absolute;
  top: 0; left: 0; right: 0;
  padding: 30px 40px;
  display: flex; justify-content: space-between;
  font-family: var(--font-mono), monospace;
  font-size: 11px; letter-spacing: 0.1em;
}
.nav-link { color: rgba(255, 255, 255, 0.6); text-decoration: none; transition: color 0.3s; }
.nav-link:hover { color: #fff; }
.nav-right { display: flex; gap: 30px; }
.about-content {
  max-width: 600px;
  text-align: center;
}
.cinematic-title { font-size: 48px; margin-bottom: 24px; }
.hero-desc { font-size: 18px; color: #A0A0A0; line-height: 1.6; }
.footer-links { margin-top: 60px; }
.footer-link {
  color: rgba(255, 255, 255, 0.4);
  font-size: 12px;
  text-decoration: none;
  font-family: var(--font-mono), monospace;
  letter-spacing: 0.05em;
}
.footer-link:hover { color: rgba(255, 255, 255, 0.8); }
</style>
