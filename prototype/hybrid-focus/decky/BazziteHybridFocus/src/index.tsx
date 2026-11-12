import {
  ButtonItem,
  PanelSection,
  PanelSectionRow,
  staticClasses,
} from "@decky/ui";
import { callable, definePlugin, toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { FaDisplay } from "react-icons/fa6";

type FocusTarget = "game" | "desktop";

type FocusStatus = {
  ok: boolean;
  target: FocusTarget;
  glyph_family?: string;
  degraded: boolean;
  message: string;
};

const getStatus = callable<[], FocusStatus>("get_status");
const setTarget = callable<[target: FocusTarget], FocusStatus>("set_target");

const glyphLabels: Record<string, string> = {
  xbox: "Xbox / Microsoft",
  playstation: "PlayStation / Sony",
  nintendo: "Nintendo / Switch",
  neutral: "Neutral",
};

function Content() {
  const [status, setStatus] = useState<FocusStatus>();
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    try {
      setStatus(await getStatus());
    } catch (error) {
      toaster.toast({
        title: "Hybrid Display Control",
        body: `Status unavailable: ${String(error)}`,
      });
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const switchTarget = async () => {
    const target: FocusTarget = status?.target === "desktop" ? "game" : "desktop";
    setBusy(true);
    try {
      const next = await setTarget(target);
      setStatus(next);
      toaster.toast({
        title: "Hybrid Display Control",
        body: next.ok ? next.message || `Controller focus: ${next.target}` : next.message,
      });
    } catch (error) {
      toaster.toast({
        title: "Hybrid Display Control",
        body: `Switch failed: ${String(error)}`,
      });
    } finally {
      setBusy(false);
    }
  };

  const family = status?.glyph_family ?? "neutral";
  const action =
    status?.target === "desktop"
      ? "Return Controller to Game"
      : "Controller to Desktop 2";

  return (
    <PanelSection title="Hybrid Display Control">
      <PanelSectionRow>
        <div>Current target: {status?.target ?? "unknown"}</div>
        <div>Controller glyphs: {glyphLabels[family] ?? "Neutral"}</div>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={busy} onClick={switchTarget}>
          {busy ? "Switching…" : action}
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
}

export default definePlugin(() => ({
  name: "Bazzite Hybrid Focus",
  titleView: <div className={staticClasses.Title}>Hybrid Display Control</div>,
  content: <Content />,
  icon: <FaDisplay />,
  onDismount() {},
}));
