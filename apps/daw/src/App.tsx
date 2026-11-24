import React from "react";
import { DawProvider } from "./commands/store";
import { I18nProvider } from "./i18n";
import { DawWorkspace } from "./workspace/DawWorkspace";

export function App() {
  return (
    <I18nProvider>
      <DawProvider>
        <DawWorkspace />
      </DawProvider>
    </I18nProvider>
  );
}
