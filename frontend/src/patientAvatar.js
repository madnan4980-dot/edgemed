// --- Verified option pools (medical/neutral subset) ---
const maleHair = ['ShortHairShortFlat', 'ShortHairShortCurly', 'ShortHairShortRound', 'ShortHairTheCaesar']
const femaleHair = ['LongHairStraight', 'LongHairBob', 'LongHairBun', 'LongHairCurly']
const hairColors = ['Black', 'BrownDark', 'Brown', 'DarkBrown']
const skinColors = ['Light', 'Brown', 'DarkBrown', 'Pale']
const clotheTypes = ['ShirtCrewNeck', 'ShirtVNeck', 'BlazerShirt']
const clotheColors = ['Blue03', 'Gray02', 'Heather', 'PastelBlue', 'PastelGreen']
const facialHairOptions = ['Blank', 'Blank', 'Blank', 'BeardLight', 'BeardMedium']
const accessoryOptions = ['Blank', 'Blank', 'Blank', 'Prescription01', 'Prescription02']

function hashString(str) {
  let h = 0
  for (let i = 0; i < str.length; i++) {
    h = (Math.imul(31, h) + str.charCodeAt(i)) | 0
  }
  return h >>> 0
}

function mulberry32(seed) {
  let a = seed
  return function () {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function pick(rng, arr) {
  return arr[Math.floor(rng() * arr.length)]
}

export function getPatientGenderInfo(patient) {
  const raw = String(patient?.gender_en || patient?.gender || patient?.gender_bn || '')
    .trim()
    .toLowerCase()

  if (raw.startsWith('f') || raw === 'মহিলা') {
    return { isMale: false, label: 'Female' }
  }
  if (raw.startsWith('m') || raw === 'পুরুষ') {
    return { isMale: true, label: 'Male' }
  }

  // Gemma should be the single source of truth for gender. If the field is
  // missing or malformed, fall back to Male by default (consistent with
  // previous behaviour being conservative). No name-based guessing.
  return { isMale: true, label: 'Male' }
}

export function getPatientAvatarProps(patient) {
  if (!patient) return null

  const seedKey = String(
    patient.id ?? `${patient.name_en ?? ''}-${patient.age ?? ''}-${patient.gender_en ?? ''}`
  )
  const rng = mulberry32(hashString(seedKey))

  const { isMale } = getPatientGenderInfo(patient)
  const elderly = (patient.age ?? 0) > 60

  return {
    avatarStyle: 'Transparent',
    topType: isMale
      ? elderly
        ? 'NoHair'
        : pick(rng, maleHair)
      : pick(rng, femaleHair),
    hairColor: elderly && isMale ? 'SilverGray' : pick(rng, hairColors),
    accessoriesType: pick(rng, accessoryOptions),
    facialHairType: isMale ? pick(rng, facialHairOptions) : 'Blank',
    facialHairColor: pick(rng, hairColors),
    clotheType: pick(rng, clotheTypes),
    clotheColor: pick(rng, clotheColors),
    eyeType: 'Default',
    eyebrowType: 'Default',
    mouthType: 'Sad',
    skinColor: pick(rng, skinColors),
  }
}
