import valueParser from 'postcss-value-parser'
import { charcoalThemeVariables, colorRole, darkCssColor, parseColor, themedColor } from '../src/theme/palette.js'

export default function workbenchTheme() {
  return {
    postcssPlugin: 'sxdevops-workbench-theme',
    Once(root) {
      const source = root.source?.input.file?.replaceAll('\\', '/') || ''
      if (source.endsWith('/src/assets/theme.css')) {
        root.append(`html[data-theme="charcoal"] { ${charcoalThemeVariables()} }`)
      }
    },
    Declaration(declaration) {
      const source = declaration.source?.input.file?.replaceAll('\\', '/') || ''
      if (!source.includes('/src/')) return
      if (!/color|background|border|outline|shadow|fill|stroke|^--/.test(declaration.prop)) return
      if (declaration.value.includes('light-dark(')) return
      const selector = declaration.parent.selector || ''
      const themeOverrides = source.endsWith('/assets/theme.css')
      if (!themeOverrides && (selector.includes('.dark') || selector.includes('data-theme'))) return
      const role = colorRole(declaration.prop)
      const mapColor = value => themeOverrides ? darkCssColor(value, role) : themedColor(value, role)
      const parsed = valueParser(declaration.value)
      parsed.walk(node => {
        if (node.type === 'function' && ['url', 'var', 'light-dark'].includes(node.value)) return false
        if (node.type === 'function' && /^rgba?$/.test(node.value)) {
          const original = valueParser.stringify(node)
          const mapped = mapColor(original)
          if (mapped !== original) {
            node.type = 'word'
            node.value = mapped
            delete node.nodes
          }
          return false
        }
        if (node.type === 'word' && parseColor(node.value)) {
          node.value = mapColor(node.value)
        }
      })
      declaration.value = parsed.toString()
    },
  }
}
