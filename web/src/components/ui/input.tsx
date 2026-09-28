import * as React from "react"
import { Input as InputPrimitive } from "@base-ui/react/input"

import { cn } from "@/lib/utils"

// Product field recipe (settings / command palette), not the registry demo:
// rounded-xl surface, compact desktop height, 44px on coarse pointers.
function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <InputPrimitive
      type={type}
      data-slot="input"
      className={cn(
        "h-9 w-full min-w-0 rounded-xl border border-border/70 bg-background/70 px-3 text-base text-foreground outline-none transition-colors placeholder:text-muted-foreground focus-visible:shadow-[var(--focus-ring)] disabled:opacity-50 aria-invalid:border-destructive md:text-sm [@media(hover:none)]:h-11",
        className
      )}
      {...props}
    />
  )
}

export { Input }
