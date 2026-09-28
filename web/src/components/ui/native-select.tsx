import * as React from "react"
import { ChevronDownIcon } from "lucide-react"

import { cn } from "@/lib/utils"

function NativeSelect({
  className,
  ...props
}: React.ComponentProps<"select">) {
  return (
    <div
      data-slot="native-select-wrapper"
      className={cn("relative grid w-full", className)}
    >
      <select
        data-slot="native-select"
        className="peer col-start-1 row-start-1 h-9 w-full min-w-0 appearance-none rounded-xl border border-border/70 bg-background/70 py-0 ps-3 pe-8 text-base text-foreground outline-none transition-colors placeholder:text-muted-foreground focus-visible:shadow-[var(--focus-ring)] disabled:opacity-50 aria-invalid:border-destructive md:text-sm [@media(hover:none)]:h-11"
        {...props}
      />
      <ChevronDownIcon
        aria-hidden="true"
        data-slot="native-select-icon"
        className="pointer-events-none col-start-1 row-start-1 me-2.5 size-4 self-center justify-self-end text-muted-foreground peer-disabled:opacity-50"
      />
    </div>
  )
}

function NativeSelectOption({
  className,
  ...props
}: React.ComponentProps<"option">) {
  return (
    <option
      data-slot="native-select-option"
      className={className}
      {...props}
    />
  )
}

function NativeSelectOptGroup({
  className,
  ...props
}: React.ComponentProps<"optgroup">) {
  return (
    <optgroup
      data-slot="native-select-optgroup"
      className={className}
      {...props}
    />
  )
}

export { NativeSelect, NativeSelectOptGroup, NativeSelectOption }
