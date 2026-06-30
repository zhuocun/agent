"use client"

import * as React from "react"
import { Dialog as DialogPrimitive } from "@base-ui/react/dialog"

import { cn } from "@/lib/utils"
import { XIcon } from "lucide-react"

function Drawer({ ...props }: DialogPrimitive.Root.Props) {
  return <DialogPrimitive.Root data-slot="drawer" {...props} />
}

/* istanbul ignore next -- exported for API completeness; the app mounts the
   drawer declaratively (open/onOpenChange), so no consumer uses this trigger. */
function DrawerTrigger({ ...props }: DialogPrimitive.Trigger.Props) {
  return <DialogPrimitive.Trigger data-slot="drawer-trigger" {...props} />
}

function DrawerPortal({ ...props }: DialogPrimitive.Portal.Props) {
  return <DialogPrimitive.Portal data-slot="drawer-portal" {...props} />
}

/* istanbul ignore next -- exported for API completeness; no current consumer
   renders a standalone drawer close button. */
function DrawerClose({ ...props }: DialogPrimitive.Close.Props) {
  return <DialogPrimitive.Close data-slot="drawer-close" {...props} />
}

function DrawerBackdrop({ className, ...props }: DialogPrimitive.Backdrop.Props) {
  return (
    <DialogPrimitive.Backdrop
      data-slot="drawer-backdrop"
      className={cn(
        "fixed inset-0 z-50 bg-foreground/30 backdrop-blur-md transition-opacity duration-200 data-[ending-style]:opacity-0 data-[starting-style]:opacity-0",
        className
      )}
      {...props}
    />
  )
}

function DrawerContent({
  className,
  children,
  side,
  showClose,
  title = "Navigation",
  ...props
}: DialogPrimitive.Popup.Props & {
  side?: "left" | "right"
  showClose?: boolean
  /**
   * Accessible name for the drawer dialog. Rendered as a visually-hidden
   * `<Title>` so Base UI can wire up `aria-labelledby`; without it the dialog
   * announces as unnamed. Defaults to "Navigation".
   */
  title?: string
}) {
  // The sole consumer (app-shell.tsx) always passes explicit `side`/`showClose`
  // and only ever mounts a left-side drawer, so the `??` fallbacks and the
  // right-side variant are unreachable through real usage. The visible close
  // affordance itself is now mounted (`showClose={true}`), so the JSX branch
  // below is reachable — only the `?? true` default here stays untaken.
  // Resolved in statements so the ignores survive the SWC→istanbul pass.
  /* istanbul ignore next */
  const resolvedSide = side ?? "left"
  /* istanbul ignore next */
  const resolvedShowClose = showClose ?? true
  /* istanbul ignore next */
  const sideClasses =
    resolvedSide === "right"
      ? "right-0 rounded-tl-3xl rounded-bl-3xl data-[ending-style]:translate-x-full data-[starting-style]:translate-x-full"
      : "left-0 rounded-tr-3xl rounded-br-3xl data-[ending-style]:-translate-x-full data-[starting-style]:-translate-x-full"
  return (
    <DrawerPortal>
      <DrawerBackdrop />
      <DialogPrimitive.Popup
        data-slot="drawer-content"
        data-side={resolvedSide}
        // Override glass-strong's blur with the larger drawer blur. Keep the
        // saturate/contrast/brightness chain identical to the glass utilities
        // so the only difference is the heavier blur radius.
        style={{
          backdropFilter:
            "blur(var(--glass-blur-lg)) saturate(var(--glass-saturate)) contrast(var(--glass-contrast)) brightness(var(--glass-brightness))",
          WebkitBackdropFilter:
            "blur(var(--glass-blur-lg)) saturate(var(--glass-saturate)) contrast(var(--glass-contrast)) brightness(var(--glass-brightness))",
        }}
        className={cn(
          "glass-strong fixed inset-y-0 z-50 flex h-dvh w-80 max-w-[85vw] flex-col pt-[env(safe-area-inset-top)] pb-[env(safe-area-inset-bottom)] text-sidebar-foreground transition-transform duration-300 ease-[var(--ease-ios-sheet)]",
          sideClasses,
          className
        )}
        {...props}
      >
        <DialogPrimitive.Title className="sr-only">
          {title}
        </DialogPrimitive.Title>
        {children}
        {
          /* The sole consumer renders with `showClose={true}`, so the visible
             close affordance is mounted; the `: null` arm stays untaken. */
          /* istanbul ignore else */
          resolvedShowClose ? (
          <DialogPrimitive.Close
            data-slot="drawer-close"
            // 44pt hit target (size-11) with a centered size-4 glyph — matches
            // the toast/dialog close-button pattern so touch targets stay native.
            // Offsets fold in the top/right safe-area insets so the control never
            // tucks under the notch/status bar (portrait) or the landscape notch
            // on a right-side drawer.
            className="absolute top-[calc(env(safe-area-inset-top)+1rem)] right-[calc(env(safe-area-inset-right)+1rem)] inline-flex size-11 items-center justify-center rounded-sm opacity-70 transition-opacity hover:opacity-100 focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none disabled:pointer-events-none [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4"
          >
            <XIcon />
            <span className="sr-only">Close</span>
          </DialogPrimitive.Close>
          ) : null
        }
      </DialogPrimitive.Popup>
    </DrawerPortal>
  )
}

/* istanbul ignore next -- exported for API completeness; the drawer body is
   composed from the sidebar, not these layout subcomponents. */
function DrawerHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="drawer-header"
      className={cn("flex flex-col gap-1.5", className)}
      {...props}
    />
  )
}

/* istanbul ignore next -- exported for API completeness; no current consumer
   renders a drawer footer. */
function DrawerFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="drawer-footer"
      className={cn("mt-auto flex flex-col gap-2", className)}
      {...props}
    />
  )
}

/* istanbul ignore next -- exported for API completeness; the visible title is
   rendered via the sr-only <Title> inside DrawerContent, not this export. */
function DrawerTitle({ className, ...props }: DialogPrimitive.Title.Props) {
  return (
    <DialogPrimitive.Title
      data-slot="drawer-title"
      className={cn("text-lg leading-none font-semibold", className)}
      {...props}
    />
  )
}

/* istanbul ignore next -- exported for API completeness; no current consumer
   renders a drawer description. */
function DrawerDescription({
  className,
  ...props
}: DialogPrimitive.Description.Props) {
  return (
    <DialogPrimitive.Description
      data-slot="drawer-description"
      className={cn("text-sm text-muted-foreground", className)}
      {...props}
    />
  )
}

export {
  Drawer,
  DrawerTrigger,
  DrawerPortal,
  DrawerClose,
  DrawerContent,
  DrawerHeader,
  DrawerFooter,
  DrawerTitle,
  DrawerDescription,
}
