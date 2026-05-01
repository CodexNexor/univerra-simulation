import { createApp } from 'vue'
import App from './App.vue'
import router from './router'

const app = createApp(App)

// Intersection Observer for scroll animations
const observer = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('is-revealed')
      }
    })
  },
  {
    threshold: 0.1,
    rootMargin: '0px 0px -50px 0px'
  }
)

app.directive('reveal', {
  mounted(el) {
    el.classList.add('reveal-element')
    observer.observe(el)
  },
  unmounted(el) {
    observer.unobserve(el)
  }
})

app.use(router)

app.mount('#app')
