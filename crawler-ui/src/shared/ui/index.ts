/**
 * The shared plate components (ARCH-2: the only import path into `shared/ui`).
 *
 * Each component is a `.tsx` file with a CSS Module beside it that reads the generated
 * tokens (`shared/theme/tokens.css`), so it follows the light and night plates without
 * asking which one is on.
 */
export { Button, type ButtonProps, type ButtonVariant } from "./Button/Button";
export { Field, TextInput, type FieldControlProps, type FieldProps, type TextInputProps } from "./Field/Field";
export { NumberField, type NumberFieldProps } from "./NumberField/NumberField";
export { parseNumberText, type ParsedNumber } from "./NumberField/parseNumberText";
export {
  GlossaryProvider,
  Term,
  type GlossaryDefinitions,
  type GlossaryProviderProps,
  type TermProps,
} from "./Term/Term";
