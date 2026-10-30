import { useId, type ComponentPropsWithRef, type ReactNode } from "react";

import { classNames } from "../classNames";
import { sharedUiMessages } from "../messages";
import styles from "./Field.module.css";

/** What a field hands its control so the label, hint and error are announced with it. */
export interface FieldControlProps {
  id: string;
  "aria-describedby": string | undefined;
  "aria-invalid": true | undefined;
  required: boolean | undefined;
}

export interface FieldProps {
  /** The visible label; a field always has one (WCAG 3.3.2). */
  label: ReactNode;
  /** One sentence on what to enter, shown under the label. */
  hint?: ReactNode;
  /** What is wrong and what to type instead (UX-1). Set only while the value is invalid. */
  error?: ReactNode;
  required?: boolean;
  /** The control's id; one is made when absent. */
  id?: string;
  className?: string;
  /** Renders the control with the props it needs: `{(control) => <TextInput {...control} />}`. */
  children: (control: FieldControlProps) => ReactNode;
}

/**
 * A labelled form field: label, optional hint and error, then the control. The hint and the
 * error come before the control, so they are read before a person starts typing, and the
 * control is described by both.
 */
export function Field({ label, hint, error, required, id, className, children }: FieldProps) {
  const madeId = useId();
  const controlId = id ?? madeId;
  const hintId = `${controlId}-hint`;
  const errorId = `${controlId}-error`;
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ");
  const invalid = Boolean(error);

  return (
    <div className={classNames(styles.field, className)}>
      <label htmlFor={controlId} className={styles.label}>
        {label}
        {required ? <span className={styles.required}> ({sharedUiMessages.required})</span> : null}
      </label>
      {hint ? (
        <p id={hintId} className={styles.hint}>
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} className={styles.error}>
          {error}
        </p>
      ) : null}
      {children({
        id: controlId,
        "aria-describedby": describedBy || undefined,
        "aria-invalid": invalid || undefined,
        required,
      })}
    </div>
  );
}

export interface TextInputProps extends ComponentPropsWithRef<"input"> {
  /** Draws the plum edge; `aria-invalid` from a Field sets it too. */
  invalid?: boolean;
}

/** The plate's single-line text box. Use it inside a Field, or give it an `aria-label`. */
export function TextInput({ invalid, type = "text", className, ...rest }: TextInputProps) {
  const flagged = invalid === true || rest["aria-invalid"] === true || rest["aria-invalid"] === "true";
  return (
    <input
      {...rest}
      type={type}
      aria-invalid={flagged || undefined}
      className={classNames(styles.input, className)}
    />
  );
}
