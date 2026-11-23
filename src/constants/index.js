import {
  BarChart3,
  Bell,
  Blocks,
  ClipboardList,
  Cloud,
  CodeXml,
  FileText,
  FolderKanban,
  History,
  LayoutDashboard,
  LifeBuoy,
  Megaphone,
  MessageSquare,
  Palette,
  PenLine,
  PlusCircle,
  Search,
  Settings,
  ShieldCheck,
  Smartphone,
  Star,
  UserRound,
  Users,
  Video,
  Wallet,
} from 'lucide-react'

export const categories = [
  {
    id: 'development',
    label: 'พัฒนาเว็บ & Backend',
    description: 'Frontend, Backend, API, Database',
    icon: CodeXml,
    accent: 'from-blue-500 to-cyan-500',
  },
  {
    id: 'mobile',
    label: 'แอปมือถือ',
    description: 'iOS, Android, Flutter, React Native',
    icon: Smartphone,
    accent: 'from-sky-500 to-indigo-500',
  },
  {
    id: 'blockchain',
    label: 'Blockchain & Smart Contract',
    description: 'Solidity, Web3, DApp, Audit',
    icon: Blocks,
    accent: 'from-amber-500 to-orange-500',
  },
  {
    id: 'design',
    label: 'ออกแบบ UX/UI',
    description: 'Product design, Design System, Prototype',
    icon: Palette,
    accent: 'from-violet-500 to-indigo-500',
  },
  {
    id: 'data',
    label: 'ข้อมูล & AI',
    description: 'Data pipeline, Dashboard, Machine Learning',
    icon: BarChart3,
    accent: 'from-emerald-500 to-teal-500',
  },
  {
    id: 'devops',
    label: 'DevOps & Cloud',
    description: 'CI/CD, Docker, Cloud, Security',
    icon: Cloud,
    accent: 'from-rose-500 to-pink-500',
  },
]

// No longer offered when posting a job, but kept so postings made earlier still show a label.
const legacyCategories = [
  { id: 'writing', label: 'เขียนเนื้อหา', icon: PenLine },
  { id: 'marketing', label: 'การตลาด', icon: Megaphone },
  { id: 'video', label: 'วิดีโอ & Motion', icon: Video },
]

export const categoryMap = Object.fromEntries(
  [...categories, ...legacyCategories].map((category) => [category.id, category]),
)

/** Suggested skills per category. The job form offers these first and falls back to free typing. */
export const skillCatalog = {
  development: [
    'React', 'Next.js', 'Vue.js', 'TypeScript', 'JavaScript', 'Node.js', 'Python', 'FastAPI',
    'Django', 'Laravel', 'Java', 'Spring Boot', 'Go', 'PostgreSQL', 'MySQL', 'MongoDB', 'GraphQL',
    'Tailwind CSS',
  ],
  mobile: [
    'Flutter', 'Dart', 'React Native', 'Swift', 'Kotlin', 'Android', 'iOS', 'Firebase', 'Expo',
    'App Store Release',
  ],
  blockchain: [
    'Solidity', 'Smart Contract', 'Ethereum', 'Hardhat', 'Foundry', 'ethers.js', 'Web3.js', 'DApp',
    'ERC-20', 'ERC-721', 'Smart Contract Audit', 'Wallet Integration', 'IPFS',
  ],
  design: [
    'Figma', 'UI Design', 'UX Research', 'Design System', 'Prototyping', 'Wireframe', 'User Flow',
    'Usability Testing', 'Responsive Design', 'Accessibility',
  ],
  data: [
    'SQL', 'Python', 'Pandas', 'Data Analysis', 'Data Visualization', 'Power BI', 'Tableau', 'ETL',
    'Apache Airflow', 'Machine Learning', 'PyTorch', 'TensorFlow', 'LLM / Prompt Engineering',
  ],
  devops: [
    'Docker', 'Kubernetes', 'AWS', 'Google Cloud', 'Azure', 'CI/CD', 'GitHub Actions', 'Terraform',
    'Linux', 'Nginx', 'Monitoring', 'Cybersecurity', 'Penetration Testing',
  ],
}

/** Skills that fit any category; shown after the category's own suggestions. */
export const commonSkills = [
  'Git', 'REST API', 'Agile / Scrum', 'Software Testing', 'Code Review', 'Technical Documentation',
]

export const allSkills = [...Object.values(skillCatalog).flat(), ...commonSkills]

/** Shortcut chips on the freelancer directory. */
export const popularSkills = [
  'React', 'Node.js', 'Python', 'Flutter', 'Solidity', 'Figma', 'Docker', 'SQL',
]

export const jobStatus = {
  open: { label: 'เปิดรับข้อเสนอ', tone: 'emerald' },
  in_progress: { label: 'กำลังดำเนินการ', tone: 'blue' },
  closed: { label: 'ปิดรับแล้ว', tone: 'slate' },
  draft: { label: 'ฉบับร่าง', tone: 'amber' },
}

export const proposalStatus = {
  pending: { label: 'รอพิจารณา', tone: 'amber' },
  shortlisted: { label: 'ผ่านการคัดเลือก', tone: 'blue' },
  hired: { label: 'ได้รับงาน', tone: 'emerald' },
  rejected: { label: 'ไม่ผ่าน', tone: 'rose' },
  withdrawn: { label: 'ถอนข้อเสนอแล้ว', tone: 'slate' },
}

export const projectStatus = {
  active: { label: 'กำลังทำ', tone: 'blue' },
  in_review: { label: 'รอตรวจรับ', tone: 'amber' },
  revision: { label: 'ขอแก้ไข', tone: 'rose' },
  completed: { label: 'เสร็จสิ้น', tone: 'emerald' },
  disputed: { label: 'มีข้อพิพาท', tone: 'rose' },
}

export const escrowStatus = {
  unfunded: { label: 'ยังไม่ฝากเงิน', tone: 'slate' },
  pending_verification: { label: 'กำลังยืนยันเงินฝาก', tone: 'amber' },
  funded: { label: 'ฝากเงินแล้ว', tone: 'blue' },
  released: { label: 'จ่ายเงินแล้ว', tone: 'emerald' },
  refunded: { label: 'คืนเงินแล้ว', tone: 'amber' },
  resolved: { label: 'ข้อพิพาทสิ้นสุดแล้ว', tone: 'slate' },
}

export const transactionStatus = {
  pending: { label: 'รอดำเนินการ', tone: 'amber' },
  confirmed: { label: 'ยืนยันแล้ว', tone: 'emerald' },
  failed: { label: 'ไม่สำเร็จ', tone: 'rose' },
}

export const transactionTypes = {
  escrow_deposit: 'ฝากเงินเข้า Escrow',
  release: 'อนุมัติจ่ายเงิน',
  earning: 'รายได้จากงาน',
  withdrawal: 'ถอนเงิน',
  refund: 'คืนเงิน',
  fee: 'ค่าธรรมเนียมแพลตฟอร์ม',
}

export const budgetTypes = [
  { value: 'fixed', label: 'ราคาเหมารวม' },
  { value: 'hourly', label: 'คิดรายชั่วโมง' },
]

export const experienceLevels = [
  { value: 'entry', label: 'ระดับเริ่มต้น' },
  { value: 'intermediate', label: 'ระดับกลาง' },
  { value: 'expert', label: 'ระดับผู้เชี่ยวชาญ' },
]

/** Preset project lengths. The job stores the label text, so "other" is plain free text. */
export const durationOptions = [
  'ไม่เกิน 1 สัปดาห์',
  '1-2 สัปดาห์',
  '2-4 สัปดาห์',
  '1-3 เดือน',
  '3-6 เดือน',
  'มากกว่า 6 เดือน',
]

/**
 * Role templates for the freelancer profile, grouped by job category. The profile form offers these
 * first and falls back to free text; the category also decides which skills get suggested.
 */
export const freelancerTitleGroups = [
  {
    category: 'development',
    options: ['Frontend Developer', 'Backend Developer', 'Full-Stack Developer', 'QA / Test Engineer'],
  },
  { category: 'mobile', options: ['Mobile App Developer', 'Flutter Developer', 'React Native Developer'] },
  {
    category: 'blockchain',
    options: ['Smart Contract Developer', 'Web3 / DApp Developer', 'Smart Contract Auditor'],
  },
  { category: 'design', options: ['UX/UI Designer', 'Product Designer', 'UX Researcher'] },
  { category: 'data', options: ['Data Analyst', 'Data Engineer', 'Machine Learning Engineer'] },
  { category: 'devops', options: ['DevOps Engineer', 'Cloud Engineer', 'Security Engineer'] },
].map((group) => ({ ...group, label: categoryMap[group.category].label }))

export const freelancerTitleCategory = Object.fromEntries(
  freelancerTitleGroups.flatMap((group) => group.options.map((title) => [title, group.category])),
)

/** Hourly rates (THB) offered as a dropdown before falling back to a typed amount. */
export const hourlyRateOptions = [300, 500, 800, 1000, 1500, 2000, 3000, 5000]

export const remoteLocation = 'ทำงานระยะไกล (Remote)'

export const thaiProvinces = [
  'กรุงเทพมหานคร', 'กระบี่', 'กาญจนบุรี', 'กาฬสินธุ์', 'กำแพงเพชร', 'ขอนแก่น', 'จันทบุรี', 'ฉะเชิงเทรา',
  'ชลบุรี', 'ชัยนาท', 'ชัยภูมิ', 'ชุมพร', 'เชียงราย', 'เชียงใหม่', 'ตรัง', 'ตราด', 'ตาก', 'นครนายก',
  'นครปฐม', 'นครพนม', 'นครราชสีมา', 'นครศรีธรรมราช', 'นครสวรรค์', 'นนทบุรี', 'นราธิวาส', 'น่าน',
  'บึงกาฬ', 'บุรีรัมย์', 'ปทุมธานี', 'ประจวบคีรีขันธ์', 'ปราจีนบุรี', 'ปัตตานี', 'พระนครศรีอยุธยา',
  'พะเยา', 'พังงา', 'พัทลุง', 'พิจิตร', 'พิษณุโลก', 'เพชรบุรี', 'เพชรบูรณ์', 'แพร่', 'ภูเก็ต',
  'มหาสารคาม', 'มุกดาหาร', 'แม่ฮ่องสอน', 'ยโสธร', 'ยะลา', 'ร้อยเอ็ด', 'ระนอง', 'ระยอง', 'ราชบุรี',
  'ลพบุรี', 'ลำปาง', 'ลำพูน', 'เลย', 'ศรีสะเกษ', 'สกลนคร', 'สงขลา', 'สตูล', 'สมุทรปราการ',
  'สมุทรสงคราม', 'สมุทรสาคร', 'สระแก้ว', 'สระบุรี', 'สิงห์บุรี', 'สุโขทัย', 'สุพรรณบุรี',
  'สุราษฎร์ธานี', 'สุรินทร์', 'หนองคาย', 'หนองบัวลำภู', 'อ่างทอง', 'อำนาจเจริญ', 'อุดรธานี',
  'อุตรดิตถ์', 'อุทัยธานี', 'อุบลราชธานี',
]

export const availabilityOptions = [
  { value: 'open', label: 'เปิดรับงาน', tone: 'emerald' },
  { value: 'limited', label: 'รับงานจำกัด', tone: 'amber' },
  { value: 'unavailable', label: 'ไม่รับงานชั่วคราว', tone: 'slate' },
]

export const clientNav = [
  { label: 'ภาพรวม', to: '/client/dashboard', icon: LayoutDashboard },
  { label: 'ประกาศงาน', to: '/client/jobs', icon: ClipboardList },
  { label: 'สร้างประกาศงาน', to: '/client/jobs/new', icon: PlusCircle },
  { label: 'โครงการที่ดูแล', to: '/client/projects', icon: FolderKanban },
  { label: 'ประวัติการจ้าง', to: '/client/history', icon: History },
  { label: 'โปรไฟล์', to: '/client/profile', icon: UserRound },
]

export const freelancerNav = [
  { label: 'ภาพรวม', to: '/freelancer/dashboard', icon: LayoutDashboard },
  { label: 'ค้นหางาน', to: '/freelancer/jobs', icon: Search },
  { label: 'ข้อเสนอของฉัน', to: '/freelancer/proposals', icon: FileText },
  { label: 'โครงการ', to: '/freelancer/projects', icon: FolderKanban },
  { label: 'รายได้', to: '/freelancer/earnings', icon: Wallet },
  { label: 'รีวิว', to: '/freelancer/reviews', icon: Star },
  { label: 'โปรไฟล์', to: '/freelancer/profile', icon: Settings },
]

export const sharedNav = [
  { label: 'ข้อความ', to: '/messages', icon: MessageSquare },
  { label: 'แจ้งเตือน', to: '/notifications', icon: Bell },
  { label: 'กระเป๋าเงิน', to: '/wallet', icon: Wallet },
  { label: 'ตั้งค่า', to: '/settings', icon: Settings },
  { label: 'เรื่องที่แจ้ง', to: '/support/tickets', icon: FileText },
  { label: 'ช่วยเหลือ', to: '/help', icon: LifeBuoy },
]

export const adminNav = [
  { label: 'ผู้ใช้', to: '/admin/users', icon: Users },
  { label: 'ประกาศงาน', to: '/admin/jobs', icon: ClipboardList },
  { label: 'รายงานปัญหา', to: '/admin/reports', icon: ShieldCheck },
]

const accountSection = { label: 'บัญชี & เครื่องมือ', items: sharedNav }

export const dashboardNavigation = {
  client: {
    workspace: 'Client workspace',
    sections: [{ label: 'การจ้างงาน', items: clientNav }, accountSection],
    marketplaceTools: true,
  },
  freelancer: {
    workspace: 'Freelancer workspace',
    sections: [{ label: 'งานของฉัน', items: freelancerNav }, accountSection],
    marketplaceTools: true,
  },
  admin: {
    workspace: 'Admin workspace',
    sections: [{ label: 'การจัดการระบบ', items: adminNav }],
    marketplaceTools: false,
  },
}

export const publicNav = [
  { label: 'ค้นหางาน', to: '/jobs' },
  { label: 'ฟรีแลนซ์', to: '/freelancers' },
  { label: 'วิธีใช้งาน', to: '/how-it-works' },
  { label: 'ช่วยเหลือ', to: '/help' },
]
