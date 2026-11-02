const active = new Map<Animation, HTMLElement>();
const held = new Set<HTMLElement>();

export function registerFeedbackMotion(animation: Animation, element: HTMLElement) {
  active.set(animation, element);
  if ([...held].some(root => root.contains(element))) animation.pause();
  return () => active.delete(animation);
}

export function holdFeedbackMotion(root: HTMLElement) {
  held.add(root);
  for (const [animation, element] of active) {
    if (root.contains(element) && animation.playState === "running") animation.pause();
  }
}

export function releaseFeedbackMotion(root: HTMLElement) {
  held.delete(root);
  for (const [animation, element] of active) {
    if (root.contains(element) && animation.playState === "paused" && ![...held].some(other => other.contains(element))) animation.play();
  }
}
