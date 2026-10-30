export const darkPalette = {
  canvas: '#101722',
  surface: '#182334',
  subtle: '#1d2a3d',
  raised: '#26364b',
  primary: '#edf2fa',
  secondary: '#becce0',
  muted: '#a5b7d0',
  border: '#607694',
  blue: '#91bfff',
  cyan: '#73d9e5',
  green: '#79dfb3',
  yellow: '#f6d37a',
  orange: '#ffbf8a',
  red: '#ffabab',
  purple: '#c5b1ff',
  pink: '#f3ace0',
  sidebarEnd: '#141e2e',
  activeSurface: '#223e63',
  overlay: '#223147',
  fillExtraLight: '#1b283a',
  fillDark: '#33465f',
  fillDarker: '#40536f',
  fillDisabled: '#202d40',
  regular: '#d0dced',
  disabled: '#8192ab',
  borderSubtle: '#2b3d55',
  borderStrong: '#6e849f',
  mask: '#0c131e',
  scrollbar: '#526680',
  scrollbarHover: '#7891b2',
  control: '#152032',
  controlBorder: '#627a99',
  controlHover: '#8aa8d0',
  tabActive: '#254365',
  tabBorder: '#5d7ea5',
  tableHeader: '#24344b',
  tableHover: '#293f5c',
  tableBorder: '#354963',
  disabledButton: '#293e5b',
  infoHover: '#4b607e',
  avatarStart: '#315c6a',
  avatarEnd: '#2a4d7c',
  chipSurface: '#233851',
  chipBorder: '#627fa6',
  graphSurface: '#152235',
  shadowHighlight: '#a0badf',
  surfaceHighlight: '#b9cce6',
}

export const charcoalPalette = {
  ...darkPalette,
  canvas: '#181818',
  surface: '#212121',
  subtle: '#262626',
  raised: '#303030',
  primary: '#f1f1f1',
  secondary: '#d0d0d0',
  muted: '#b5b5b5',
  border: '#787878',
  sidebarEnd: '#1b1b1b',
  activeSurface: '#343434',
  overlay: '#2c2c2c',
  fillExtraLight: '#242424',
  fillDark: '#3b3b3b',
  fillDarker: '#4a4a4a',
  fillDisabled: '#2a2a2a',
  regular: '#e0e0e0',
  disabled: '#989898',
  borderSubtle: '#363636',
  borderStrong: '#8b8b8b',
  mask: '#101010',
  scrollbar: '#686868',
  scrollbarHover: '#939393',
  control: '#1c1c1c',
  controlBorder: '#797979',
  controlHover: '#a1a1a1',
  tabActive: '#383838',
  tabBorder: '#777777',
  tableHeader: '#303030',
  tableHover: '#393939',
  tableBorder: '#454545',
  disabledButton: '#343434',
  infoHover: '#585858',
  avatarStart: '#464646',
  avatarEnd: '#343434',
  chipSurface: '#363636',
  chipBorder: '#7a7a7a',
  graphSurface: '#202020',
  shadowHighlight: '#cccccc',
  surfaceHighlight: '#dddddd',
  codeSurface: '#171717',
}

export function themePalette(theme) {
  return theme === 'charcoal' ? charcoalPalette : darkPalette
}

export function parseColor(value) {
  if (typeof value !== 'string') return null
  const source = value.trim().toLowerCase()
  if (source === 'white') return { red: 255, green: 255, blue: 255, alpha: 1 }
  if (source === 'black') return { red: 0, green: 0, blue: 0, alpha: 1 }
  if (/^#[\da-f]{3,4}$/.test(source)) {
    return parseColor(`#${source.slice(1).split('').map(character => character.repeat(2)).join('')}`)
  }
  if (/^#[\da-f]{6}([\da-f]{2})?$/.test(source)) {
    return {
      red: parseInt(source.slice(1, 3), 16),
      green: parseInt(source.slice(3, 5), 16),
      blue: parseInt(source.slice(5, 7), 16),
      alpha: source.length === 9 ? parseInt(source.slice(7, 9), 16) / 255 : 1,
    }
  }
  const match = source.match(/^rgba?\(([^()]+)\)$/)
  if (!match) return null
  const channels = match[1].split(/[,\s/]+/).filter(Boolean)
  if (channels.length < 3 || channels.length > 4) return null
  const channelValue = channel => parseFloat(channel) * (channel.endsWith('%') ? 2.55 : 1)
  const alphaValue = channels[3] || '1'
  const result = {
    red: channelValue(channels[0]),
    green: channelValue(channels[1]),
    blue: channelValue(channels[2]),
    alpha: parseFloat(alphaValue) / (alphaValue.endsWith('%') ? 100 : 1),
  }
  return Object.values(result).every(Number.isFinite) ? result : null
}

function colorTone(color) {
  const red = color.red / 255
  const green = color.green / 255
  const blue = color.blue / 255
  const maximum = Math.max(red, green, blue)
  const minimum = Math.min(red, green, blue)
  const difference = maximum - minimum
  const lightness = (maximum + minimum) / 2
  const saturation = difference === 0 ? 0 : difference / (1 - Math.abs(2 * lightness - 1))
  let hue = 0
  if (difference) {
    if (maximum === red) hue = ((green - blue) / difference + 6) % 6
    else if (maximum === green) hue = (blue - red) / difference + 2
    else hue = (red - green) / difference + 4
    hue *= 60
  }
  const neutral = saturation < 0.26 || (hue >= 200 && hue <= 245 && saturation < 0.65 && maximum < 0.72)
  let tone = 'blue'
  if (hue < 18 || hue >= 345) tone = 'red'
  else if (hue < 45) tone = 'orange'
  else if (hue < 75) tone = 'yellow'
  else if (hue < 165) tone = 'green'
  else if (hue < 195) tone = 'cyan'
  else if (hue < 255) tone = 'blue'
  else if (hue < 295) tone = 'purple'
  else tone = 'pink'
  return { lightness, neutral, tone, minimum, maximum }
}

function withAlpha(value, alpha) {
  if (alpha >= 1) return value
  const color = parseColor(value)
  return `rgba(${color.red}, ${color.green}, ${color.blue}, ${Number(alpha.toFixed(3))})`
}

export function darkColor(value, role = 'text', palette = darkPalette) {
  const color = parseColor(value)
  if (!color || color.alpha === 0) return value
  const { lightness, neutral, tone, minimum } = colorTone(color)
  if (role === 'shadow') {
    return withAlpha(minimum > 0.8 ? palette.shadowHighlight : '#000000', minimum > 0.8 ? Math.min(color.alpha, 0.06) : Math.max(color.alpha, 0.2))
  }
  if (role === 'border') {
    return withAlpha(neutral || lightness > 0.85 ? palette.border : palette[tone], Math.max(color.alpha, 0.48))
  }
  if (role === 'surface') {
    if (lightness < 0.27 && color.alpha > 0.6) return palette.codeSurface && (neutral || tone === 'blue') ? withAlpha(palette.codeSurface, color.alpha) : value
    if (lightness > 0.8) {
      if (color.alpha < 0.3 && minimum > 0.9) return withAlpha(palette.surfaceHighlight, Math.min(color.alpha, 0.08))
      const surface = lightness > 0.99 ? palette.surface : lightness > 0.95 ? palette.subtle : palette.raised
      return withAlpha(surface, color.alpha)
    }
    if (color.alpha < 0.65) return withAlpha(neutral ? palette.border : palette[tone], Math.max(color.alpha, 0.12))
    if (neutral) return withAlpha(palette.raised, color.alpha)
    const channel = value => Math.round(value * 0.75)
    return `rgba(${channel(color.red)}, ${channel(color.green)}, ${channel(color.blue)}, ${color.alpha})`
  }
  if (minimum > 0.88) return value
  const foreground = neutral
    ? lightness < 0.3 ? palette.primary : lightness < 0.58 ? palette.secondary : palette.muted
    : palette[tone]
  return withAlpha(foreground, Math.max(color.alpha, 0.82))
}

export function colorRole(property) {
  if (/shadow/i.test(property)) return 'shadow'
  if (/border|outline|stroke|splitLine|axisLine/i.test(property)) return 'border'
  if (/background|(^|[-_])bg($|[-_])|fill|surface|track|mask|overlay|panel|soft$|gradient|sidebar-(active|hover)$/i.test(property)) return 'surface'
  return 'text'
}

export function themedColor(value, role = 'text') {
  const mapped = darkCssColor(darkColor(value, role), role)
  return mapped === value ? value : `light-dark(${value}, ${mapped})`
}

export function darkCssColor(value, role = 'text') {
  const color = parseColor(value)
  if (!color || color.alpha === 0) return value
  const channels = `${color.red} ${color.green} ${color.blue}`
  const entry = Object.entries(darkPalette).find(([, paletteColor]) => {
    const candidate = parseColor(paletteColor)
    return candidate.red === color.red && candidate.green === color.green && candidate.blue === color.blue
  })
  if (entry) return `rgb(var(--theme-${entry[0]}, ${channels}) / ${color.alpha})`
  const { lightness, neutral, tone } = colorTone(color)
  if (role === 'surface' && lightness < 0.27 && color.alpha > 0.6 && (neutral || tone === 'blue')) {
    return `rgb(var(--theme-codeSurface, ${channels}) / ${color.alpha})`
  }
  return value
}

export function charcoalThemeVariables() {
  return Object.entries(charcoalPalette).map(([key, value]) => {
    const color = parseColor(value)
    return `--theme-${key}: ${color.red} ${color.green} ${color.blue};`
  }).join('\n')
}
