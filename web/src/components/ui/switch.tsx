"use client"

import { Switch as SwitchPrimitive } from "@base-ui/react/switch"

import { haptic } from "@/lib/use-haptic"
import { cn } from "@/lib/utils"

function Switch({ className, onCheckedChange, ...props }: SwitchPrimitive.Root.Props) {
  // Haptic shim: fire a subtle selection buzz on every toggle commit so all
  // consumers (settings toggles, composer chips) get native-feel feedback for
  // free. Feature-detected + no-op on iOS, so it's safe to call unconditionally.
  const handleCheckedChange: SwitchPrimitive.Root.Props["onCheckedChange"] = (
    checked,
    event,
  ) => {
    haptic("selection")
    onCheckedChange?.(checked, event)
  }
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      onCheckedChange={handleCheckedChange}
      className={cn(
        "group relative inline-flex h-5 w-9 shrink-0 items-center rounded-full border border-border bg-muted/60 transition-colors outline-none focus-visible:shadow-[var(--focus-ring)] disabled:cursor-not-allowed disabled:opacity-50 data-[checked]:border-transparent data-[checked]:bg-brand",
        "before:absolute before:left-1/2 before:top-1/2 before:h-11 before:w-11 before:-translate-x-1/2 before:-translate-y-1/2 before:content-['']",
        className
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb
        data-slot="switch-thumb"
        className="pointer-events-none block size-4 translate-x-0.5 rounded-full bg-card shadow-glass-ambient transition-transform duration-[250ms] ease-ios-spring group-active:scale-95 motion-reduce:ease-out motion-reduce:duration-150 motion-reduce:group-active:scale-100 data-[checked]:translate-x-4"
      />
    </SwitchPrimitive.Root>
  )
}

export { Switch }
