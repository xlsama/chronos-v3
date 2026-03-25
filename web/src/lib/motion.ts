// 页面进入动画
export const pageVariants = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
}

export const pageTransition = { duration: 0.1, ease: "easeOut" }

// 列表容器（stagger children）
export const listVariants = {
  initial: {},
  animate: { transition: { staggerChildren: 0.02 } },
}

// 列表项动画
export const listItemVariants = {
  initial: { opacity: 0, y: 4 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.1 } },
}

// 卡片网格项动画（稍微大一点的位移）
export const cardItemVariants = {
  initial: { opacity: 0, y: 6, scale: 0.99 },
  animate: { opacity: 1, y: 0, scale: 1, transition: { duration: 0.12 } },
}

// 内容过渡动画（skeleton → content / empty 渐变切换）
export const contentFadeVariants = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
}
export const contentFadeTransition = { duration: 0.15 }

