import type { ComponentPropsWithRef, ReactNode } from "react";

import { classNames } from "../classNames";
import styles from "./Button.module.css";

/**
 * - `outline`: the default plate control, a hairline ink edge on the ground.
 * - `primary`: the one main action of a page or form; ink filled and at least 44px tall.
 * - `quiet`: a secondary action set as text, for rows and toolbars that already have an outline button.
 */
export type ButtonVariant = "outline" | "primary" | "quiet";

export interface ButtonProps extends Omit<ComponentPropsWithRef<"button">, "children"> {
  variant?: ButtonVariant;
  /**
   * Makes the button a toggle (`aria-pressed`). A pressed outline button is drawn ink
   * filled, as the Measurements and speed toggles are. Leave it undefined for a plain action.
   */
  pressed?: boolean;
  children: ReactNode;
}

/**
 * The one button of the plate. It is a real `button`, `type="button"` unless a form asks
 * for `submit`, so a button inside a form never submits it by accident.
 */
export function Button({
  variant = "outline",
  pressed,
  type = "button",
  className,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      type={type}
      aria-pressed={pressed}
      className={classNames(styles.button, styles[variant], className)}
    >
      {children}
    </button>
  );
}
