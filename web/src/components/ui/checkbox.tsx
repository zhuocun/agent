"use client"

import { Checkbox as CheckboxPrimitive } from "@base-ui/react/checkbox"
import { CheckIcon } from "lucide-react"

import { cn } from "@/lib/utils"

// A small accessible checkbox built on base-ui, matching the other `ui/`
// wrappers (Conversation Org v2 multi-select). Controlled via `checked` +
// `onCheckedChange`; renders a check glyph in the indicator when ticked.
function Checkbox({ className, ...props }: CheckboxPrimitive.Root.Props) {
  return (
    <CheckboxPrimitive.Root
      data-slot="checkbox"
      className={cn(
        "peer relative flex size-4 shrink-0 items-center justify-center rounded-[4px] border border-border bg-card text-card outline-none transition-colors focus-visible:shadow-[var(--focus-ring)] disabled:cursor-not-allowed disabled:opacity-50 data-[checked]:border-brand data-[checked]:bg-brand data-[checked]:text-primary-foreground",
        "[@media(hover:none)]:before:absolute [@media(hover:none)]:before:top-1/2 [@media(hover:none)]:before:left-1/2 [@media(hover:none)]:before:h-11 [@media(hover:none)]:before:w-11 [@media(hover:none)]:before:-translate-x-1/2 [@media(hover:none)]:before:-translate-y-1/2 [@media(hover:none)]:before:content-['']",
        className
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator
        data-slot="checkbox-indicator"
        className="flex items-center justify-center text-current"
      >
        <CheckIcon className="size-3" strokeWidth={3} />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  )
}

export { Checkbox }
