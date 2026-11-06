import { Suspense, type ReactNode } from "react";
import { Shell } from "@/components/studio/Shell";
import { StudioProvider } from "@/components/studio/StudioProvider";

/** The static shell shown on a page load until the URL params are known (Cache Components). */
function ShellFallback() {
  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[18rem_1fr]">
      <div className="border-line hidden border-r lg:block" />
      <div role="status" aria-label="Loading" className="mx-auto w-full max-w-6xl px-6 py-14 lg:px-12">
        <div className="skeleton h-16 w-72 rounded-2xl" />
        <div className="skeleton mt-4 h-4 w-96 max-w-full" />
      </div>
    </div>
  );
}

export default function StudioLayout({ children }: { children: ReactNode }) {
  return (
    <Suspense fallback={<ShellFallback />}>
      <StudioProvider>
        <Shell>{children}</Shell>
      </StudioProvider>
    </Suspense>
  );
}
