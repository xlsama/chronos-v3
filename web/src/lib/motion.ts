// 页面进入动画
export const pageVariants = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
}

export const pageTransition = { duration: 0.3, ease: "easeOut" }

// 列表容器（stagger children）
export const listVariants = {
  initial: {},
  animate: { transition: { staggerChildren: 0.04 } },
}

// 列表项动画
export const listItemVariants = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.25 } },
}

// 卡片网格项动画（稍微大一点的位移）
export const cardItemVariants = {
  initial: { opacity: 0, y: 12, scale: 0.98 },
  animate: { opacity: 1, y: 0, scale: 1, transition: { duration: 0.3 } },
}
