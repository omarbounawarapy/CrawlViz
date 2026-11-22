import { useId, useState, type ComponentPropsWithRef } from "react";

import { classNames } from "../classNames";
import { TextInput } from "../Field/Field";
import { sharedUiMessages } from "../messages";
import { numberToEditableText, parseNumberText } from "./parseNumberText";
import styles from "./NumberField.module.css";

type NativeInputProps = Omit<
  ComponentPropsWithRef<"input">,
  "value" | "defaultValue" | "onChange" | "type" | "inputMode"
>;

export interface NumberFieldProps extends NativeInputProps {
  value: number | null;
  /** Called only with a value that parses: a number, or `null` for an empty box when `nullable`. */
  onChange: (value: number | null) => void;
  /** An empty box means "no value" (`null`). Otherwise an empty box asks for a number. */
  nullable?: boolean;
  /** Only whole numbers are accepted, and phones show a digits keypad. */
  integer?: boolean;
  /** Read after the value: "pages", "s", "%". */
  unit?: string;
  /** Draws the box as invalid for a reason the caller knows (out of range, for example). */
  invalid?: boolean;
}

/** The text being edited and the value it was typed against, so an outside change wins. */
interface Draft {
  text: string;
  base: number | null;
}

/**
 * The plate's number box. It is `type="text"`, so the browser never reformats or rounds the
 * value, accepts a dot or a comma as the decimal mark, and calls `onChange` only when the
 * text is a number. Text that is not keeps its place, and a sentence under the box says
 * what to type (WCAG 3.3.1, 3.3.3) until it is fixed.
 */
export function NumberField({
  value,
  onChange,
  nullable = false,
  integer = false,
  unit,
  invalid = false,
  className,
  "aria-describedby": describedByCaller,
  ...rest
}: NumberFieldProps) {
  const [draft, setDraft] = useState<Draft | null>(null);
  const uid = useId();
  const unitId = `${uid}-unit`;
  const problemId = `${uid}-problem`;

  const editing = draft !== null && draft.base === value;
  const text = editing ? draft.text : numberToEditableText(value);
  const problem = editing ? problemWith(draft.text, nullable, integer) : null;
  const describedBy = [describedByCaller, unit ? unitId : null, problem ? problemId : null].filter(Boolean).join(" ");

  const handleChange = (typed: string) => {
    const parsed = parseNumberText(typed);
    if (!parsed.ok || problemWith(typed, nullable, integer) !== null) {
      setDraft({ text: typed, base: value });
      return;
    }
    setDraft({ text: typed, base: parsed.value });
    onChange(parsed.value);
  };

  return (
    <span className={classNames(styles.root, className)}>
      <TextInput
        {...rest}
        type="text"
        inputMode={integer ? "numeric" : "decimal"}
        autoComplete="off"
        spellCheck={false}
        value={text}
        invalid={invalid || problem !== null}
        aria-describedby={describedBy || undefined}
        className={styles.input}
        onChange={(event) => {
          handleChange(event.target.value);
        }}
        onBlur={(event) => {
          // Settled text is shown in its plain form; text that is not a number stays to be fixed.
          if (problem === null) setDraft(null);
          rest.onBlur?.(event);
        }}
      />
      {unit ? (
        <span id={unitId} className={styles.unit}>
          {unit}
        </span>
      ) : null}
      {problem ? (
        <span id={problemId} className={styles.problem}>
          {problem}
        </span>
      ) : null}
    </span>
  );
}

/** The sentence that says what to type, or null when the text is an acceptable value. */
function problemWith(text: string, nullable: boolean, integer: boolean): string | null {
  const parsed = parseNumberText(text);
  const expected = integer ? sharedUiMessages.wholeNumberExpected : sharedUiMessages.numberExpected;
  if (!parsed.ok) return expected;
  if (parsed.value === null) return nullable ? null : expected;
  if (integer && !Number.isInteger(parsed.value)) return expected;
  return null;
}
