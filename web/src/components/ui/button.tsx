import { Button as ButtonPrimitive } from "@base-ui/react/button"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const interactiveVariant =
  "transition-[transform,box-shadow,background-color,color,filter] duration-[280ms] ease-ios-spring border border-transparent bg-clip-padding font-medium active:not-aria-[haspopup]:scale-[0.96] active:not-aria-[haspopup]:brightness-[0.92] active:duration-[70ms] active:ease-out motion-reduce:active:not-aria-[haspopup]:scale-100"

const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center rounded-lg whitespace-nowrap outline-none select-none focus-visible:shadow-[var(--focus-ring)] motion-reduce:transition-none disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default: cn(
          interactiveVariant,
          "bg-primary text-primary-foreground hover:bg-primary/90",
        ),
        outline: cn(
          interactiveVariant,
          "border-border bg-background hover:bg-muted hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground dark:border-input dark:bg-input/30 dark:hover:bg-input/50",
        ),
        secondary: cn(
          interactiveVariant,
          "bg-secondary text-secondary-foreground hover:bg-secondary/80 aria-expanded:bg-secondary aria-expanded:text-secondary-foreground",
        ),
        ghost: cn(
          interactiveVariant,
          "hover:bg-accent hover:text-accent-foreground aria-expanded:bg-accent aria-expanded:text-accent-foreground",
        ),
        destructive: cn(
          interactiveVariant,
          "bg-destructive/10 text-destructive-text hover:bg-destructive/20 focus-visible:border-destructive/40 focus-visible:ring-destructive/20 dark:bg-destructive/20 dark:hover:bg-destructive/30 dark:focus-visible:ring-destructive/40",
        ),
        link: cn(
          interactiveVariant,
          "text-primary underline-offset-4 hover:underline",
        ),
        plain: "font-normal",
        sidebar:
          "font-medium text-sidebar-foreground transition-[transform,background-color] duration-100 ease-in-out touch-manipulation hover:bg-muted/60 active:scale-[0.97] motion-reduce:active:scale-100",
      },
      size: {
        default:
          "text-base md:text-sm h-8 gap-1.5 px-2.5 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2 [@media(hover:none)]:min-h-11",
        xs: "h-6 gap-1 rounded-[min(var(--radius-md),10px)] px-2 text-[0.8125rem] md:text-xs in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3 [@media(hover:none)]:min-h-11",
        sm: "h-7 gap-1 rounded-[min(var(--radius-md),12px)] px-2.5 text-sm md:text-[0.8rem] in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3.5 [@media(hover:none)]:min-h-11",
        lg: "text-base md:text-sm h-9 gap-1.5 px-2.5 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2 [@media(hover:none)]:min-h-11",
        icon: "text-base md:text-sm size-8 hover:-translate-y-px [@media(hover:none)]:size-11",
        "icon-xs":
          "text-base md:text-sm size-6 rounded-[min(var(--radius-md),10px)] in-data-[slot=button-group]:rounded-lg [&_svg:not([class*='size-'])]:size-3 [@media(hover:none)]:size-11",
        "icon-sm":
          "text-base md:text-sm size-7 rounded-[min(var(--radius-md),12px)] in-data-[slot=button-group]:rounded-lg [@media(hover:none)]:size-11",
        "icon-lg": "text-base md:text-sm size-9 hover:-translate-y-px [@media(hover:none)]:size-11",
        bare: "h-auto min-h-0 border-0 p-0",
        sidebar:
          "flex h-auto min-h-11 w-full shrink justify-start gap-2 rounded-2xl px-3 py-2 text-left ui-list-row whitespace-normal",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
