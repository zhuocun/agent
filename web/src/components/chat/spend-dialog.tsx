"use client";

import { useState, type JSX } from "react";
import { BarChart3 } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { SpendAnalyticsPanel } from "@/components/chat/spend-analytics-panel";

export { SpendAnalyticsPanel } from "@/components/chat/spend-analytics-panel";

/** Modal wrapper kept for deep-links; Settings embeds `SpendAnalyticsPanel` inline. */
export function SpendDialog(): JSX.Element {
  const [open, setOpen] = useState(false);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button
            type="button"
            variant="secondary"
            size="sm"
            data-testid="spend-dialog-trigger"
          >
            <BarChart3 aria-hidden className="size-3.5" />
            <span>View spend details</span>
          </Button>
        }
      />
      <DialogContent className="sm:max-w-xl" data-testid="spend-dialog">
        <DialogHeader>
          <DialogTitle>Spend details</DialogTitle>
          <DialogDescription>
            Longitudinal model spend over the selected window.
          </DialogDescription>
        </DialogHeader>
        <div className="-mr-2 max-h-[60dvh] overflow-y-auto pr-2 sm:max-h-[70dvh]">
          <SpendAnalyticsPanel active={open} />
        </div>
      </DialogContent>
    </Dialog>
  );
}
