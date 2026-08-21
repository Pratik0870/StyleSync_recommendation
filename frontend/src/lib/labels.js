/**
 * Presentation-only vocabulary.
 *
 * These map the backend's taxonomy values onto human labels for display. They
 * deliberately contain no logic: no scoring, no ordering, no filtering. If a
 * value is not listed, it is title-cased rather than hidden, so a new backend
 * category shows up rather than silently disappearing.
 */

const CATEGORY_LABELS = {
  beauty_lip: 'Lips',
  beauty_eye: 'Eyes',
  beauty_face: 'Face',
  beauty_nails: 'Nails',
  beauty_skincare: 'Skincare',
  beauty_hair: 'Hair',
  beauty_tools: 'Beauty tools',
  fragrance: 'Fragrance',
  jewellery: 'Jewellery',
  bag: 'Bags',
  wallet: 'Wallets',
  watch: 'Watches',
  eyewear: 'Eyewear',
  belt: 'Belts',
  headwear: 'Headwear',
  neckwear: 'Scarves & dupattas',
  footwear_dress: 'Heels',
  footwear_flat: 'Flats & sandals',
  footwear_formal: 'Formal shoes',
  footwear_casual: 'Casual shoes',
  footwear_sports: 'Sports shoes',
  ethnic_wear: 'Ethnic wear',
  topwear: 'Topwear',
  bottomwear: 'Bottomwear',
  dress: 'Dresses',
  outerwear: 'Outerwear',
  apparel_set: 'Sets',
  loungewear: 'Loungewear',
  innerwear: 'Innerwear',
  accessory_other: 'Accessories',
}

/** Grouping used only to order sections on the results page. */
const CATEGORY_FAMILY = {
  beauty_lip: 'Beauty',
  beauty_eye: 'Beauty',
  beauty_face: 'Beauty',
  beauty_nails: 'Beauty',
  beauty_skincare: 'Beauty',
  beauty_hair: 'Beauty',
  beauty_tools: 'Beauty',
  fragrance: 'Beauty',
  jewellery: 'Accessories',
  bag: 'Accessories',
  wallet: 'Accessories',
  watch: 'Accessories',
  eyewear: 'Accessories',
  belt: 'Accessories',
  headwear: 'Accessories',
  neckwear: 'Accessories',
  accessory_other: 'Accessories',
  footwear_dress: 'Footwear',
  footwear_flat: 'Footwear',
  footwear_formal: 'Footwear',
  footwear_casual: 'Footwear',
  footwear_sports: 'Footwear',
}

const titleCase = (value) =>
  String(value ?? '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())

export const categoryLabel = (key) => CATEGORY_LABELS[key] ?? titleCase(key)
export const categoryFamily = (key) => CATEGORY_FAMILY[key] ?? 'More'

/** Colour families the backend uses, with a swatch for each. */
export const COLOUR_SWATCH = {
  black: '#1a1a1a',
  white: '#ffffff',
  grey: '#808080',
  beige: '#e8d9b0',
  brown: '#7b4b27',
  red: '#d0021b',
  pink: '#ff6fa8',
  purple: '#6b3fa0',
  blue: '#1f6feb',
  green: '#2e7d32',
  yellow: '#f8e71c',
  orange: '#f5811f',
  gold: '#d4af37',
  silver: '#c0c0c0',
  multi: 'conic-gradient(#d0021b,#f8e71c,#2e7d32,#1f6feb,#6b3fa0,#d0021b)',
}

export const COLOUR_OPTIONS = Object.keys(COLOUR_SWATCH)

export const OCCASION_OPTIONS = [
  'wedding',
  'festive',
  'party',
  'formal',
  'office',
  'casual',
  'sports',
]

export const STYLE_OPTIONS = [
  'elegant',
  'minimal',
  'bold',
  'traditional',
  'modern',
  'glam',
]

export const GENDER_OPTIONS = ['women', 'men', 'unisex']

/** Categories a user can ask for or rule out, grouped for the picker. */
export const CATEGORY_PICKER = [
  { family: 'Beauty', keys: ['beauty_lip', 'beauty_eye', 'beauty_face', 'beauty_nails', 'fragrance'] },
  { family: 'Accessories', keys: ['jewellery', 'bag', 'watch', 'eyewear', 'neckwear', 'belt'] },
  { family: 'Footwear', keys: ['footwear_dress', 'footwear_flat', 'footwear_formal', 'footwear_casual'] },
]

/** Human labels for the engine's score components. */

/** Browse destinations in the header. Each maps to real /browse filters. */
export const BROWSE_SECTIONS = {
  wardrobe: {
    title: 'Wardrobe',
    lede: 'Pick something you already own, and Match will build the rest of the look around it.',
    params: { anchorsOnly: true },
    anchorable: true,
  },
  beauty: {
    title: 'Beauty',
    lede: 'Lip, eye, face and nail colour, chosen to work with what you are wearing.',
    params: { domain: 'beauty' },
  },
  accessories: {
    title: 'Accessories',
    lede: 'Jewellery, bags and the finishing pieces that lift a look.',
    params: { domain: 'accessory' },
  },
  footwear: {
    title: 'Footwear',
    lede: 'Heels, flats, formal and casual — the half of the look people forget.',
    params: { domain: 'footwear' },
  },
}

/** Confidence wording that matches what the backend actually reported. */
export const CONFIDENCE_COPY = {
  strong: { label: 'Plenty to choose from', tone: 'text-ink-faint' },
  moderate: { label: 'A good selection', tone: 'text-ink-faint' },
  thin: { label: 'Limited choice here', tone: 'text-gold' },
  none: { label: 'Nothing suitable found', tone: 'text-berry' },
}

/** Catalog product types are plural; a single card reads better in the singular. */
const SINGULAR_TYPE = {
  Shirts: 'shirt', Tshirts: 't-shirt', Sarees: 'saree', Kurtas: 'kurta',
  Kurtis: 'kurti', Dresses: 'dress', Tops: 'top', Trousers: 'trousers',
  Jeans: 'jeans', Shorts: 'shorts', Heels: 'heels', Flats: 'flats',
  Sandals: 'sandals', Watches: 'watch', Sunglasses: 'sunglasses',
  Handbags: 'handbag', Clutches: 'clutch', Belts: 'belt', Socks: 'socks',
  Caps: 'cap', Backpacks: 'backpack', Sweaters: 'sweater',
  Sweatshirts: 'sweatshirt', Tracksuits: 'tracksuit', Jackets: 'jacket',
  Skirts: 'skirt', Leggings: 'leggings', Earrings: 'earrings',
  'Sports Shoes': 'running shoes', 'Formal Shoes': 'formal shoes',
  'Casual Shoes': 'casual shoes', 'Track Pants': 'track pants',
  'Perfume and Body Mist': 'fragrance', 'Nehru Jackets': 'nehru jacket',
}

export function productLabel(product) {
  const type = product.product_type
  const noun = SINGULAR_TYPE[type] || (type || '').toLowerCase()
  return [product.colour, noun].filter(Boolean).join(' ')
}
