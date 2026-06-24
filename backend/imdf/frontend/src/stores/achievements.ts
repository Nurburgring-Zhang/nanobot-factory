/**
 * R3.5-W2 stub: 成就事件追踪
 */

export type AchievementEventType =
  | 'hidden_mode.enabled'
  | (string & {});

export interface AchievementEvent {
  type: AchievementEventType;
  theme?: string;
  kind?: string;
  mode?: string;
  [key: string]: unknown;
}

export function trackAchievementEvent(event: AchievementEvent): void {
  // stub: 后续可接入真正的成就系统
  void event;
}
