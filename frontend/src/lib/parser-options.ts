export type SelectOption = { name: string; slug?: string; alias?: string };
export type OlxLocationGroup = { region: string; cities: { name: string; slug: string }[] };
export type KrishaLocation = {
  name: string;
  alias: string;
  type: "country" | "city" | "region";
  cities?: KrishaLocationChild[];
  districts?: KrishaLocationChild[];
};
export type KrishaLocationChild = { name: string; alias: string; districts?: KrishaLocationChild[] };
export type KrishaFilterState = {
  dealType: string;
  propertyType: string;
  rooms: string;
  priceFrom: string;
  priceTo: string;
  hasPhoto: boolean;
  newBuildings: boolean;
  fromOwner: boolean;
  fromAgent: boolean;
};

export const KRISHA_DEAL_TYPES = [
  { label: "Купить", value: "prodazha" },
  { label: "Арендовать", value: "arenda" },
];

export const KRISHA_PROPERTY_TYPES = [
  { label: "Квартиру", value: "kvartiry" },
  { label: "Дом или дачу", value: "doma-dachi" },
  { label: "Гараж или паркинг", value: "garazhi" },
  { label: "Участок", value: "uchastkov" },
  { label: "Коммерческую недвижимость", value: "kommercheskaya-nedvizhimost" },
  { label: "Бизнес", value: "biznes" },
  { label: "Промбазу или завод", value: "prombazy" },
  { label: "Зарубежную недвижимость", value: "zarubezhnoj-nedvizhimosti" },
];

export const KRISHA_ROOM_OPTIONS = [
  { label: "Любая комнатность", value: "" },
  { label: "1 комната", value: "1" },
  { label: "2 комнаты", value: "2" },
  { label: "3 комнаты", value: "3" },
  { label: "4 комнаты", value: "4" },
  { label: "5+ комнат", value: "5.100" },
];

export const DEFAULT_KRISHA_FILTERS: KrishaFilterState = {
  dealType: "prodazha",
  propertyType: "kvartiry",
  rooms: "",
  priceFrom: "",
  priceTo: "",
  hasPhoto: false,
  newBuildings: false,
  fromOwner: false,
  fromAgent: false,
};

export const OLX_LOCATIONS: OlxLocationGroup[] = [
  {
    region: "Популярные города",
    cities: [
      { name: "Алматы", slug: "alma-ata" },
      { name: "Астана", slug: "astana" },
      { name: "Шымкент", slug: "shymkent" },
      { name: "Караганда", slug: "karaganda" },
      { name: "Актобе", slug: "aktobe" },
      { name: "Павлодар", slug: "pavlodar" },
      { name: "Тараз", slug: "taraz" },
      { name: "Усть-Каменогорск", slug: "ust-kamenogorsk" },
      { name: "Атырау", slug: "atyrau" },
      { name: "Костанай", slug: "kostanay" },
      { name: "Актау", slug: "aktau" },
      { name: "Семей", slug: "semey" },
      { name: "Кызылорда", slug: "kyzylorda" },
      { name: "Уральск", slug: "uralsk" },
      { name: "Петропавловск", slug: "petropavlovsk" },
      { name: "Кокшетау", slug: "kokshetau" },
      { name: "Туркестан", slug: "turkestan" },
      { name: "Талдыкорган", slug: "taldykorgan" },
      { name: "Каскелен", slug: "kaskelen" },
      { name: "Талгар", slug: "talgar" },
    ],
  },
  {
    region: "Алматинская область",
    cities: [
      { name: "Конаев (Капчагай)", slug: "kapshagay_1485" },
      { name: "Есик", slug: "esik" },
      { name: "Жаркент", slug: "zharkent" },
      { name: "Текели", slug: "tekeli" },
      { name: "Шелек", slug: "shelek" },
      { name: "Боралдай", slug: "boralday" },
      { name: "Отеген батыра", slug: "otegen-batyr" },
    ],
  },
];

export const KRISHA_LOCATIONS: KrishaLocation[] = [
  { name: "Весь Казахстан", alias: "", type: "country", cities: [], districts: [] },
  {
    name: "Алматы",
    alias: "almaty",
    type: "city",
    cities: [],
    districts: [
      { name: "Алатауский р-н", alias: "almaty-alatauskij" },
      { name: "Алмалинский р-н", alias: "almaty-almalinskij" },
      { name: "Ауэзовский р-н", alias: "almaty-aujezovskij" },
      { name: "Бостандыкский р-н", alias: "almaty-bostandykskij" },
      { name: "Жетысуский р-н", alias: "almaty-zhetysuskij" },
      { name: "Медеуский р-н", alias: "almaty-medeuskij" },
      { name: "Наурызбайский р-н", alias: "almaty-nauryzbajskiy" },
      { name: "Турксибский р-н", alias: "almaty-turksibskij" },
    ],
  },
  {
    name: "Астана",
    alias: "astana",
    type: "city",
    cities: [],
    districts: [
      { name: "Алматы р-н", alias: "astana-almatinskij" },
      { name: "Есильский р-н", alias: "astana-esilskij" },
      { name: "Нура р-н", alias: "astana-nura" },
      { name: "р-н Байконур", alias: "r-n-bajkonur" },
      { name: "Сарайшык р-н", alias: "astana-saraishyk" },
      { name: "Сарыарка р-н", alias: "astana-saryarkinskij" },
    ],
  },
  {
    name: "Шымкент",
    alias: "shymkent",
    type: "city",
    cities: [],
    districts: [
      { name: "Абайский р-н", alias: "shymkent-abajskij" },
      { name: "Аль-Фарабийский р-н", alias: "shymkent-al-farabijskij" },
      { name: "Енбекшинский р-н", alias: "shymkent-enbekshinskij" },
      { name: "Каратауский р-н", alias: "karatauskij" },
      { name: "Туран р-н", alias: "shymkent-turan" },
    ],
  },
  { name: "Абай обл.", alias: "abay-oblast", type: "region", cities: [{ name: "Семей", alias: "semej" }, { name: "Курчатов", alias: "kurchatov" }, { name: "Аягоз", alias: "ajagoz" }] },
  { name: "Актюбинская обл.", alias: "aktjubinskaja-oblast", type: "region", cities: [{ name: "Актобе", alias: "aktobe" }, { name: "Хромтау", alias: "hromtau" }, { name: "Кандыагаш", alias: "kandagash" }] },
  { name: "Алматинская обл.", alias: "almatinskaja-oblast", type: "region", cities: [{ name: "Конаев", alias: "konaev" }, { name: "Каскелен", alias: "kaskelen" }, { name: "Талгар", alias: "talgar" }, { name: "Есик", alias: "esik" }, { name: "Жаркент", alias: "zharkent" }, { name: "Узынагаш", alias: "uzynagash" }] },
  { name: "Атырауская обл.", alias: "atyrauskaja-oblast", type: "region", cities: [{ name: "Атырау", alias: "atyrau" }, { name: "Кульсары", alias: "kulsary" }] },
  { name: "Восточно-Казахстанская обл.", alias: "vostochno-kazahstanskaja-oblast", type: "region", cities: [{ name: "Усть-Каменогорск", alias: "ust-kamenogorsk" }, { name: "Риддер", alias: "ridder" }, { name: "Алтай", alias: "altaj" }] },
  { name: "Жамбылская обл.", alias: "zhambylskaja-oblast", type: "region", cities: [{ name: "Тараз", alias: "taraz" }, { name: "Шу", alias: "shu" }, { name: "Жанатас", alias: "zhanatas" }, { name: "Каратау", alias: "karatau" }] },
  { name: "Жетысу обл.", alias: "jetisyskaya-oblast", type: "region", cities: [{ name: "Талдыкорган", alias: "taldykorgan" }, { name: "Текели", alias: "tekeli" }, { name: "Сарканд", alias: "sarkand" }, { name: "Ушарал", alias: "usharal" }] },
  { name: "Западно-Казахстанская обл.", alias: "zapadno-kazahstanskaja-oblast", type: "region", cities: [{ name: "Уральск", alias: "uralsk" }, { name: "Аксай", alias: "aksaj" }] },
  { name: "Карагандинская обл.", alias: "karagandinskaja-oblast", type: "region", cities: [{ name: "Караганда", alias: "karaganda" }, { name: "Темиртау", alias: "temirtau" }, { name: "Балхаш", alias: "balhash" }, { name: "Сарань", alias: "saran" }, { name: "Шахтинск", alias: "shahtinsk" }] },
  { name: "Костанайская обл.", alias: "kostanajskaja-oblast", type: "region", cities: [{ name: "Костанай", alias: "kostanaj" }, { name: "Рудный", alias: "rudnyj" }, { name: "Лисаковск", alias: "lisakovsk" }] },
  { name: "Кызылординская обл.", alias: "kyzylordinskaja-oblast", type: "region", cities: [{ name: "Кызылорда", alias: "kyzylorda" }, { name: "Байконур", alias: "bajkonur" }] },
  { name: "Мангистауская обл.", alias: "mangistauskaja-oblast", type: "region", cities: [{ name: "Актау", alias: "aktau" }, { name: "Жанаозен", alias: "zhanaozen" }] },
  { name: "Павлодарская обл.", alias: "pavlodarskaja-oblast", type: "region", cities: [{ name: "Павлодар", alias: "pavlodar" }, { name: "Экибастуз", alias: "jekibastuz" }, { name: "Аксу", alias: "aksu" }] },
  { name: "Северо-Казахстанская обл.", alias: "severo-kazahstanskaja-oblast", type: "region", cities: [{ name: "Петропавловск", alias: "petropavlovsk" }] },
  { name: "Туркестанская обл.", alias: "juzhno-kazahstanskaja-oblast", type: "region", cities: [{ name: "Туркестан", alias: "turkestan" }, { name: "Кентау", alias: "kentau" }, { name: "Арыс", alias: "arys" }, { name: "Сарыагаш", alias: "saryagash" }] },
  { name: "Улытауская обл.", alias: "ulitayskay-oblast", type: "region", cities: [{ name: "Жезказган", alias: "zhezkazgan" }, { name: "Сатпаев", alias: "satpaev" }] },
  { name: "Акмолинская обл.", alias: "akmolinskaja-oblast", type: "region", cities: [{ name: "Кокшетау", alias: "kokshetau" }, { name: "Степногорск", alias: "stepnogorsk" }, { name: "Щучинск", alias: "shhuchinsk" }] },
];

export const OLX_LOCATION_SLUGS = new Set(OLX_LOCATIONS.flatMap((group) => group.cities.map((city) => city.slug)));
export const KRISHA_LOCATION_ALIASES = new Set(
  KRISHA_LOCATIONS.flatMap((item) => [
    item.alias,
    ...(item.cities || []).map((city) => city.alias),
    ...(item.districts || []).map((district) => district.alias),
    ...(item.cities || []).flatMap((city) => (city.districts || []).map((district) => district.alias)),
  ]).filter(Boolean),
);

export function buildOlxCategoryUrl(l1: string, l2 = "", l3 = "", location = ""): string {
  const parts = [l1, l2, l3, location].filter(Boolean);
  return parts.length ? `https://www.olx.kz/${parts.join("/")}/` : "";
}

export function parseOlxUrlPath(rawUrl: string): { l1: string; l2: string; l3: string; location: string } {
  const fallback = { l1: "", l2: "", l3: "", location: "" };
  const match = String(rawUrl || "").trim().match(/^https?:\/\/(?:www\.)?olx\.kz\/([^?#]+)$/i);
  if (!match) return fallback;
  const parts = match[1].replace(/\/+$/, "").split("/").filter(Boolean);
  const location = OLX_LOCATION_SLUGS.has(parts[parts.length - 1]) ? parts.pop() || "" : "";
  return { l1: parts[0] || "", l2: parts[1] || "", l3: parts[2] || "", location };
}

export function build2gisSearchUrl(domain: string, city: string, rubric: string): string {
  const safeDomain = (domain || "kz").trim().toLowerCase() || "kz";
  const safeCity = (city || "astana").trim() || "astana";
  const safeRubric = (rubric || "").trim();
  if (!safeRubric) return "";
  return `https://2gis.${safeDomain}/${encodeURIComponent(safeCity)}/search/${encodeURIComponent(safeRubric)}`;
}

export function parse2gisSearchUrl(rawUrl: string): { domain: string; city: string; rubric: string } {
  const fallback = { domain: "kz", city: "astana", rubric: "" };
  const match = String(rawUrl || "").trim().match(/^https?:\/\/2gis\.([a-z.]+)\/([^/]+)\/search\/(.+)$/i);
  if (!match) return fallback;
  const safeDecode = (value: string) => {
    try {
      return decodeURIComponent(value);
    } catch {
      return value;
    }
  };
  return {
    domain: match[1] || fallback.domain,
    city: safeDecode(match[2] || fallback.city),
    rubric: safeDecode((match[3] || "").replace(/\+/g, "%20")),
  };
}

function krishaQueryString(filters: Partial<KrishaFilterState> = {}): string {
  const params = new URLSearchParams();
  const rooms = String(filters.rooms || "").trim();
  const priceFrom = String(filters.priceFrom || "").trim();
  const priceTo = String(filters.priceTo || "").trim();
  if (rooms) params.append("das[live.rooms]", rooms === "5+" ? "5.100" : rooms);
  if (priceFrom) params.set("das[price][from]", priceFrom);
  if (priceTo) params.set("das[price][to]", priceTo);
  if (filters.hasPhoto) params.set("das[_sys.hasphoto]", "1");
  if (filters.newBuildings) params.set("das[novostroiki]", "1");
  if (filters.fromOwner) params.set("das[who]", "1");
  if (filters.fromAgent) params.set("das[_sys.fromAgent]", "1");
  return params.toString().replace(/%5B/g, "[").replace(/%5D/g, "]");
}

function parseKrishaFilters(params: URLSearchParams, baseParts: string[]): KrishaFilterState {
  return {
    ...DEFAULT_KRISHA_FILTERS,
    dealType: baseParts[0] || DEFAULT_KRISHA_FILTERS.dealType,
    propertyType: baseParts[1] || DEFAULT_KRISHA_FILTERS.propertyType,
    rooms: params.get("das[live.rooms]") || "",
    priceFrom: params.get("das[price][from]") || "",
    priceTo: params.get("das[price][to]") || "",
    hasPhoto: params.get("das[_sys.hasphoto]") === "1",
    newBuildings: params.get("das[novostroiki]") === "1",
    fromOwner: params.get("das[who]") === "1",
    fromAgent: params.get("das[_sys.fromAgent]") === "1",
  };
}

export function buildKrishaListingUrl(baseParts: string[], location = "", filters: Partial<KrishaFilterState> = {}): string {
  const filterParts = [
    filters.dealType || baseParts[0] || DEFAULT_KRISHA_FILTERS.dealType,
    filters.propertyType || baseParts[1] || DEFAULT_KRISHA_FILTERS.propertyType,
  ];
  if (location) filterParts.push(location);
  const query = krishaQueryString(filters);
  return `https://krisha.kz/${filterParts.join("/")}/${query ? `?${query}` : ""}`;
}

export function parseKrishaListingUrl(rawUrl: string): { baseParts: string[]; location: string; filters: KrishaFilterState } {
  const fallback = { baseParts: ["prodazha", "kvartiry"], location: "", filters: DEFAULT_KRISHA_FILTERS };
  try {
    const url = new URL(String(rawUrl || "").trim());
    if (!/^(www\.)?krisha\.kz$/i.test(url.hostname)) return fallback;
    const parts = url.pathname.replace(/\/+$/, "").split("/").filter(Boolean);
    const location = KRISHA_LOCATION_ALIASES.has(parts[parts.length - 1]) ? parts.pop() || "" : "";
    const baseParts = parts.length ? parts : fallback.baseParts;
    return { baseParts, location, filters: parseKrishaFilters(url.searchParams, baseParts) };
  } catch {
    return fallback;
  }
}

export function findKrishaLocationByAlias(alias: string): { root: KrishaLocation; city: KrishaLocationChild | null; district: KrishaLocationChild | null } {
  if (!alias) return { root: KRISHA_LOCATIONS[0], city: null, district: null };
  for (const root of KRISHA_LOCATIONS) {
    if (root.alias === alias) return { root, city: null, district: null };
    const rootDistrict = (root.districts || []).find((district) => district.alias === alias);
    if (rootDistrict) return { root, city: null, district: rootDistrict };
    for (const city of root.cities || []) {
      if (city.alias === alias) return { root, city, district: null };
      const cityDistrict = (city.districts || []).find((district) => district.alias === alias);
      if (cityDistrict) return { root, city, district: cityDistrict };
    }
  }
  return { root: KRISHA_LOCATIONS[0], city: null, district: null };
}
