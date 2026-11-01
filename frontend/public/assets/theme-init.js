(() => {
  let savedTheme = 'charcoal'
  try {
    const preference = localStorage.getItem('sxdevops-theme')
    if (['light', 'dark', 'charcoal'].includes(preference)) savedTheme = preference
  } catch {}
  document.documentElement.classList.toggle('dark', savedTheme !== 'light')
  document.documentElement.dataset.theme = savedTheme
  document.documentElement.style.colorScheme = savedTheme === 'light' ? 'light' : 'dark'
})()
