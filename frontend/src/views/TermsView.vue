<template>
  <div class="terms-page">
    <nav class="landing-nav">
      <router-link to="/" class="nav-left nav-link">UNIVERRA</router-link>
      <div class="nav-right">
        <router-link to="/app" class="nav-link">WORK</router-link>
        <router-link to="/about" class="nav-link">ABOUT</router-link>
      </div>
    </nav>
    <div class="terms-content">
      <h1 class="main-title">Terms & Conditions</h1>
      <div class="terms-text">
        <p>Welcome to Univerra.</p>
        <p>1. <strong>Usage</strong>: The simulations provided are for predictive modeling purposes. Outputs are probabilistic forecasts and should not be taken as factual guarantees.</p>
        <p>2. <strong>Data</strong>: Any parameters or documents uploaded are securely analyzed within the simulated environment and discarded upon session termination.</p>
        <p>3. <strong>Liability</strong>: Univerra and its parent entities hold no liability over real-world decisions made based on generated reports.</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.terms-page {
  min-height: 100vh;
  background-color: var(--bg-primary);
  color: var(--text-main);
  padding: 120px 40px;
  display: flex;
  justify-content: center;
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
.terms-content {
  max-width: 800px;
  width: 100%;
}
.main-title {
  font-size: 36px;
  margin-bottom: 40px;
  padding-bottom: 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}
.terms-text p {
  font-size: 16px;
  color: #A0A0A0;
  line-height: 1.8;
  margin-bottom: 24px;
}
strong { color: #FFFFFF; }
</style>
