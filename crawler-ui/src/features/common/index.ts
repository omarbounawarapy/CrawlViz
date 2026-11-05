/**
 * The common feature's public surface (ARCH-2): the page frame, the form controls and the
 * small helpers the other features share.
 *
 * These are design-system parts that predate `shared/ui`; they move there one by one, and
 * this index shrinks as they do.
 */
export { default as EmptyState } from "./EmptyState";
export { Button, Chip, ConfirmButton, Field, Grid, Group, Select, Status, TabPanel, Tabs, TextInput } from "./Form";
export { Hint } from "./Hint";
export { Page, Row, SectionTitle } from "./Page";
export { default as ScrollRegion } from "./ScrollRegion";
export { buttonOutline, buttonPrimary } from "./buttons";
export { nextChoice } from "./choiceKeys";
export { default as useFocusableWhenScrolling } from "./useFocusableWhenScrolling";
