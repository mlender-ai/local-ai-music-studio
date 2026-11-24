import React from "react";
import { DawProvider } from "./commands/store";
import { DawWorkspace } from "./workspace/DawWorkspace";

export function App() {
  return (
    <DawProvider>
      <DawWorkspace />
    </DawProvider>
  );
}
