"use client";

import { Drawer, DrawerContent } from "@/components/ui/drawer";
import { cn } from "@/lib/utils";

export interface AppShellProps {
  sidebar: React.ReactNode; // a <Sidebar .../> element
  sidebarOpen: boolean; // desktop: persistent rail shown?
  mobileNavOpen: boolean; // mobile: drawer open?
  onMobileNavOpenChange: (open: boolean) => void;
  children: React.ReactNode; // the chat column
}

export function AppShell({
  sidebar,
  sidebarOpen,
  mobileNavOpen,
  onMobileNavOpenChange,
  children,
}: AppShellProps): React.JSX.Element {
  return (
    <div className="flex h-dvh w-full overflow-hidden bg-background">
      <aside
        className={cn(
          "hidden shrink-0 overflow-hidden transition-[width] duration-200 md:flex md:flex-col",
          sidebarOpen ? "md:w-72" : "md:w-0"
        )}
      >
        {sidebar}
      </aside>

      <Drawer open={mobileNavOpen} onOpenChange={onMobileNavOpenChange}>
        <DrawerContent side="left" showClose={false} className="w-72">
          {sidebar}
        </DrawerContent>
      </Drawer>

      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {children}
      </main>
    </div>
  );
}
