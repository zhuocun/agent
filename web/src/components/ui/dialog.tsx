"use client"

import * as React from "react"
import { Dialog as DialogPrimitive } from "@base-ui/react/dialog"

import { cn } from "@/lib/utils"
import { useSwipeDismiss } from "@/lib/use-swipe-dismiss"
import { XIcon } from "lucide-react"

function Dialog({ ...props }: DialogPrimitive.Root.Props) {
  return <DialogPrimitive.Root data-slot="dialog" {...props} />
}

function DialogTrigger({ ...props }: DialogPrimitive.Trigger.Props) {
  return <DialogPrimitive.Trigger data-slot="dialog-trigger" {...props} />
}

function DialogPortal({ ...props }: DialogPrimitive.Portal.Props) {
  return <DialogPrimitive.Portal data-slot="dialog-portal" {...props} />
}

function DialogClose({ ...props }: DialogPrimitive.Close.Props) {
  return <DialogPrimitive.Close data-slot="dialog-close" {...props} />
}

function DialogBackdrop({ className, ...props }: DialogPrimitive.Backdrop.Props) {
  return (
    <DialogPrimitive.Backdrop
      data-slot="dialog-backdrop"
      className={cn(
        "fixed inset-0 z-50 bg-foreground/45 backdrop-blur-sm transition-opacity duration-200 data-[ending-style]:opacity-0 data-[starting-style]:opacity-0",
        className
      )}
      {...props}
    />
  )
}

/**
 * Tracks whether we're below the `sm` breakpoint (640px), i.e. whether the
 * dialog should present as a bottom sheet. SSR-safe: starts `false` and syncs
 * on mount, so the markup is identical on the server and never mismatches.
 */
function useIsMobileSheet(): boolean {
  const [isMobile, setIsMobile] = React.useState(false)
  React.useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return
    const mq = window.matchMedia("(max-width: 639.98px)")
    const sync = () => setIsMobile(mq.matches)
    sync()
    mq.addEventListener("change", sync)
    return () => mq.removeEventListener("change", sync)
  }, [])
  return isMobile
}

function DialogContent({
  className,
  children,
  showGrabber = true,
  ...props
}: DialogPrimitive.Popup.Props & {
  /**
   * Render the iOS grabber pill at the top of the mobile bottom sheet. Only
   * ever visible below `sm` (`sm:hidden`); set `false` for sheets that don't
   * want it. Defaults to `true`.
   */
  showGrabber?: boolean
}) {
  const isMobile = useIsMobileSheet()
  const closeRef = React.useRef<HTMLButtonElement>(null)
  // Swipe-to-dismiss drives the dialog closed through the real Close button so
  // it goes through Base UI's own close path (focus return, onOpenChange).
  const { sheetRef, handleProps, contentProps } = useSwipeDismiss({
    enabled: isMobile,
    onDismiss: () => closeRef.current?.click(),
  })

  return (
    <DialogPortal>
      <DialogBackdrop />
      <DialogPrimitive.Popup
        ref={sheetRef}
        data-slot="dialog-content"
        // Override glass-regular's blur with the denser dialog blur. Inline
        // style wins over the utility's backdrop-filter without a new utility.
        style={{
          backdropFilter:
            "blur(var(--glass-blur-xl)) saturate(var(--glass-saturate)) contrast(var(--glass-contrast))",
          WebkitBackdropFilter:
            "blur(var(--glass-blur-xl)) saturate(var(--glass-saturate)) contrast(var(--glass-contrast))",
        }}
        className={cn(
          // Mobile (default): iOS bottom sheet — full width, pinned to the
          // bottom, rounded top only, capped height, home-indicator-safe bottom
          // padding. Slides up/down with iOS sheet easing.
          "glass-strong fixed inset-x-0 bottom-0 z-50 grid w-full gap-4 rounded-t-3xl rounded-b-none p-6 pb-[max(env(safe-area-inset-bottom),1rem)] text-foreground",
          "max-h-[90dvh] transition-[transform,opacity] duration-[400ms] ease-[cubic-bezier(0.32,0.72,0,1)] max-sm:data-[ending-style]:translate-y-full max-sm:data-[starting-style]:translate-y-full",
          // Desktop (sm+): restore the centered modal — reset the sheet anchor,
          // radius and slide, and swap back to the scale+fade transition. The
          // centering -translate keeps composing with scale during the anim.
          "sm:inset-x-auto sm:top-1/2 sm:bottom-auto sm:left-1/2 sm:max-h-none sm:max-w-lg sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-3xl sm:rounded-b-3xl sm:p-6 sm:pb-6 sm:transition-all sm:duration-200 sm:ease-out sm:data-[ending-style]:scale-95 sm:data-[ending-style]:opacity-0 sm:data-[starting-style]:scale-95 sm:data-[starting-style]:opacity-0",
          className
        )}
        {...contentProps}
        {...props}
      >
        {showGrabber ? (
          <div
            aria-hidden
            {...handleProps}
            className="-mt-2.5 mx-auto h-1.5 w-9 shrink-0 cursor-grab touch-none rounded-full bg-foreground/15 sm:hidden"
          />
        ) : null}
        {children}
        <DialogPrimitive.Close
          ref={closeRef}
          data-slot="dialog-close"
          className="absolute top-4 right-4 rounded-sm opacity-70 transition-opacity hover:opacity-100 focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none disabled:pointer-events-none [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4"
        >
          <XIcon />
          <span className="sr-only">Close</span>
        </DialogPrimitive.Close>
      </DialogPrimitive.Popup>
    </DialogPortal>
  )
}

function DialogHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="dialog-header"
      className={cn(
        "flex flex-col gap-1.5 text-center sm:text-left",
        className
      )}
      {...props}
    />
  )
}

function DialogFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="dialog-footer"
      className={cn(
        "flex flex-col-reverse gap-2 sm:flex-row sm:justify-end",
        className
      )}
      {...props}
    />
  )
}

function DialogTitle({ className, ...props }: DialogPrimitive.Title.Props) {
  return (
    <DialogPrimitive.Title
      data-slot="dialog-title"
      className={cn("text-lg leading-none font-semibold", className)}
      {...props}
    />
  )
}

function DialogDescription({
  className,
  ...props
}: DialogPrimitive.Description.Props) {
  return (
    <DialogPrimitive.Description
      data-slot="dialog-description"
      className={cn("text-sm text-muted-foreground", className)}
      {...props}
    />
  )
}

export {
  Dialog,
  DialogTrigger,
  DialogPortal,
  DialogClose,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
}
