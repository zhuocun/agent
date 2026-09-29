import * as React from "react"

import { cn } from "@/lib/utils"

// Same field surface as Input. min-h-20 is the product multi-line height; it
// stays above the 44px coarse-pointer floor on every pointer type.
function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "min-h-20 w-full resize-y rounded-xl border border-border/70 bg-background/70 px-3 py-2 text-base leading-5 text-foreground outline-none transition-colors placeholder:text-muted-foreground focus-visible:shadow-[var(--focus-ring)] disabled:opacity-50 aria-invalid:border-destructive md:text-sm [@media(hover:none)]:min-h-20",
        className
      )}
      {...props}
    />
  )
}

export { Textarea }
