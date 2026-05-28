"use client";

import { useState } from "react";

export function LiveRegion({ message }: { message: string }) {
  // Screen readers may suppress re-announcement when the rendered text is
  // identical to the previous value. When the same message is set twice in a
  // row, append a zero-width space so the DOM text node differs and the live
  // region re-announces — without changing the spoken output.
  const [prevMessage, setPrevMessage] = useState<string>("");
  const [toggle, setToggle] = useState<boolean>(false);

  if (message !== prevMessage) {
    setPrevMessage(message);
    setToggle((t) => !t);
  }

  const suffix = toggle ? "​" : "";
  const rendered = message === "" ? "" : `${message}${suffix}`;

  return (
    <div role="status" aria-live="polite" aria-atomic="true" className="sr-only">
      {rendered}
    </div>
  );
}
