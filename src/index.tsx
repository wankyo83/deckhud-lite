import {
  ButtonItem,
  DialogButton,
  DropdownItem,
  PanelSection,
  PanelSectionRow,
  SliderField,
  staticClasses,
  ToggleField,
} from "@decky/ui";
import { callable, definePlugin, toaster } from "@decky/api";
import { useEffect, useRef, useState } from "react";
import { FaBatteryThreeQuarters, FaChevronDown, FaChevronUp } from "react-icons/fa";

type Position = "top-left" | "top-right" | "bottom-left" | "bottom-right";
type Layout = "horizontal" | "vertical";
type SeparatorStyle = "pipe" | "dot" | "none";
type MetricKey = "battery" | "clock" | "fps" | "fan" | "refresh_rate" | "show_fps_limit";

interface Settings {
  enabled: boolean;
  battery: boolean;
  battery_watt: boolean;
  battery_time: boolean;
  clock: boolean;
  clock_seconds: boolean;
  fps: boolean;
  fan: boolean;
  refresh_rate: boolean;
  show_fps_limit: boolean;
  layout: Layout;
  metric_order: MetricKey[];
  vertical_separators: boolean;
  separator_style: SeparatorStyle;
  position: Position;
  font_size: number;
  background_alpha: number;
}

interface Status {
  connected: boolean;
  config_path: string;
  enabled: boolean;
}

const allMetrics: MetricKey[] = ["battery", "clock", "fps", "fan", "refresh_rate", "show_fps_limit"];
const metricLabels: Record<MetricKey, string> = {
  battery: "배터리 정보",
  clock: "현재 시각",
  fps: "FPS",
  fan: "팬 속도",
  refresh_rate: "화면 주사율",
  show_fps_limit: "설정된 FPS 제한",
};

const defaults: Settings = {
  enabled: true,
  battery: true,
  battery_watt: true,
  battery_time: true,
  clock: true,
  clock_seconds: false,
  fps: false,
  fan: false,
  refresh_rate: false,
  show_fps_limit: false,
  layout: "horizontal",
  metric_order: allMetrics,
  vertical_separators: true,
  separator_style: "pipe",
  position: "top-right",
  font_size: 20,
  background_alpha: 0.35,
};

const getSettings = callable<[], Settings>("get_settings");
const saveSettings = callable<[Settings], boolean>("save_settings");
const getStatus = callable<[], Status>("get_status");
const applyNow = callable<[], boolean>("apply_now");
const restoreOriginal = callable<[], boolean>("restore_original");

const positionOptions: { data: Position; label: string }[] = [
  { data: "top-right", label: "오른쪽 위" },
  { data: "top-left", label: "왼쪽 위" },
  { data: "bottom-right", label: "오른쪽 아래" },
  { data: "bottom-left", label: "왼쪽 아래" },
];
const layoutOptions: { data: Layout; label: string }[] = [
  { data: "horizontal", label: "수평 — 한 줄" },
  { data: "vertical", label: "수직 — 여러 줄" },
];
function Content() {
  const [settings, setSettings] = useState<Settings>(defaults);
  const [status, setStatus] = useState<Status>({ connected: false, config_path: "", enabled: true });
  const [loaded, setLoaded] = useState(false);
  const settingsRef = useRef<Settings>(defaults);
  const saveQueueRef = useRef<Promise<void>>(Promise.resolve());

  const refreshStatus = async () => setStatus(await getStatus());

  useEffect(() => {
    let active = true;
    Promise.all([getSettings(), getStatus()]).then(([saved, currentStatus]) => {
      if (!active) return;
      const savedOrder = Array.isArray(saved.metric_order) ? saved.metric_order : [];
      const order = [...savedOrder.filter((item) => allMetrics.includes(item)), ...allMetrics.filter((item) => !savedOrder.includes(item))];
      const next = { ...defaults, ...saved, metric_order: order };
      settingsRef.current = next;
      setSettings(next);
      setStatus(currentStatus);
      setLoaded(true);
    });
    const timer = window.setInterval(() => refreshStatus(), 3000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const save = (next: Settings) => {
    settingsRef.current = next;
    setSettings(next);
    const queuedSave = saveQueueRef.current.catch(() => undefined).then(async () => {
      const ok = await saveSettings(next);
      if (!ok) {
        toaster.toast({ title: "DeckHUD Lite", body: "게임 HUD를 아직 찾지 못했습니다. 게임 실행 후 자동 적용됩니다." });
      }
      await refreshStatus();
    });
    saveQueueRef.current = queuedSave;
    return queuedSave;
  };

  const update = async <K extends keyof Settings>(key: K, value: Settings[K]) => {
    await save({ ...settingsRef.current, [key]: value });
  };

  const updateBattery = async (enabled: boolean) => {
    await save({
      ...settingsRef.current,
      battery: enabled,
      battery_watt: enabled,
      battery_time: enabled,
    });
  };

  const moveMetric = async (metric: MetricKey, direction: -1 | 1) => {
    const current = settingsRef.current;
    const currentIndex = current.metric_order.indexOf(metric);
    const targetIndex = currentIndex + direction;
    if (currentIndex < 0 || targetIndex < 0 || targetIndex >= current.metric_order.length) return;
    const order = [...current.metric_order];
    [order[currentIndex], order[targetIndex]] = [order[targetIndex], order[currentIndex]];
    await save({ ...current, metric_order: order });
  };

  const metricEnabled = (metric: MetricKey) => {
    if (metric === "battery") return settings.battery || settings.battery_watt || settings.battery_time;
    if (metric === "clock") return settings.clock;
    return settings[metric];
  };

  if (!loaded) return <PanelSection title="DeckHUD Lite">설정을 불러오는 중…</PanelSection>;

  return (
    <>
      <PanelSection title="상태">
        <PanelSectionRow>
          <div style={{ padding: "4px 0", color: status.connected ? "#7ee787" : "#f0c36a" }}>
            {status.connected ? "● 게임 HUD 연결됨" : "● 게임 실행을 기다리는 중"}
          </div>
        </PanelSectionRow>
        <PanelSectionRow>
          <ToggleField label="사용" description="Steam 성능 오버레이를 아래 설정으로 자동 유지합니다." checked={settings.enabled} onChange={(v) => update("enabled", v)} />
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="배터리 정보">
        <PanelSectionRow>
          <ToggleField
            label="배터리"
            description="잔량(%) · 소비전력(W) · 예상 남은 시간을 한 묶음으로 표시합니다."
            checked={settings.battery || settings.battery_watt || settings.battery_time}
            onChange={updateBattery}
          />
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="추가 표시 항목">
        <PanelSectionRow><ToggleField label="현재 시각" checked={settings.clock} onChange={(v) => update("clock", v)} /></PanelSectionRow>
        <PanelSectionRow><ToggleField label="시계에 초 표시" disabled={!settings.clock} checked={settings.clock_seconds} onChange={(v) => update("clock_seconds", v)} /></PanelSectionRow>
        <PanelSectionRow><ToggleField label="FPS" checked={settings.fps} onChange={(v) => update("fps", v)} /></PanelSectionRow>
        <PanelSectionRow><ToggleField label="팬 속도" description="Steam Deck의 팬 RPM" checked={settings.fan} onChange={(v) => update("fan", v)} /></PanelSectionRow>
        <PanelSectionRow><ToggleField label="화면 주사율" description="현재 화면 Hz" checked={settings.refresh_rate} onChange={(v) => update("refresh_rate", v)} /></PanelSectionRow>
        <PanelSectionRow><ToggleField label="설정된 FPS 제한" checked={settings.show_fps_limit} onChange={(v) => update("show_fps_limit", v)} /></PanelSectionRow>
      </PanelSection>

      <PanelSection title="방향과 구분선">
        <PanelSectionRow>
          <DropdownItem label="HUD 방향" rgOptions={layoutOptions} selectedOption={layoutOptions.findIndex((item) => item.data === settings.layout)} onChange={(option) => update("layout", option.data)} />
        </PanelSectionRow>
        {settings.layout === "horizontal" && (
          <PanelSectionRow>
            <div style={{ opacity: 0.75, fontSize: "0.85em" }}>수평 모드는 항목 사이에 MangoHud 기본 세로선 하나를 표시합니다.</div>
          </PanelSectionRow>
        )}
        {settings.layout === "vertical" && (
          <PanelSectionRow><ToggleField label="항목 사이 가로선" checked={settings.vertical_separators} onChange={(v) => update("vertical_separators", v)} /></PanelSectionRow>
        )}
      </PanelSection>

      <PanelSection title="항목 순서">
        <style>{`
          .deckhud-order-button {
            min-width: 34px !important;
            width: 34px !important;
            height: 32px !important;
            min-height: 32px !important;
            padding: 0 !important;
            margin: 0 !important;
          }
        `}</style>
        <PanelSectionRow>
          <div style={{ opacity: 0.75, fontSize: "0.85em", paddingBottom: 6 }}>
            배터리의 세 값은 MangoHud에서 한 묶음이며, 묶음 전체의 위치를 이동합니다.
          </div>
        </PanelSectionRow>
        {settings.metric_order.map((metric, index) => (
          <PanelSectionRow key={metric}>
            <div style={{ display: "flex", alignItems: "center", width: "100%", gap: 6 }}>
              <div style={{ flex: "1 1 auto", minWidth: 0, whiteSpace: "normal", lineHeight: 1.25, opacity: metricEnabled(metric) ? 1 : 0.45 }}>
                {index + 1}. {metricLabels[metric]}{metricEnabled(metric) ? "" : " (꺼짐)"}
              </div>
              <div style={{ display: "flex", flex: "0 0 auto", gap: 4 }}>
                <DialogButton className="deckhud-order-button" disabled={index === 0} onClick={() => moveMetric(metric, -1)}>
                  <FaChevronUp size={12} />
                </DialogButton>
                <DialogButton className="deckhud-order-button" disabled={index === settings.metric_order.length - 1} onClick={() => moveMetric(metric, 1)}>
                  <FaChevronDown size={12} />
                </DialogButton>
              </div>
            </div>
          </PanelSectionRow>
        ))}
      </PanelSection>

      <PanelSection title="모양">
        <PanelSectionRow>
          <DropdownItem label="위치" rgOptions={positionOptions} selectedOption={positionOptions.findIndex((item) => item.data === settings.position)} onChange={(option) => update("position", option.data)} />
        </PanelSectionRow>
        <PanelSectionRow><SliderField label="글자 크기" min={12} max={36} step={1} value={settings.font_size} showValue onChange={(v) => update("font_size", v)} /></PanelSectionRow>
        <PanelSectionRow><SliderField label="배경 진하기" min={0} max={100} step={5} value={Math.round(settings.background_alpha * 100)} showValue onChange={(v) => update("background_alpha", v / 100)} /></PanelSectionRow>
      </PanelSection>

      <PanelSection title="복구">
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={async () => {
            const ok = await applyNow();
            toaster.toast({ title: "DeckHUD Lite", body: ok ? "HUD 설정을 다시 적용했습니다." : "실행 중인 게임 HUD를 찾지 못했습니다." });
            await refreshStatus();
          }}>지금 다시 적용</ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={async () => {
            const ok = await restoreOriginal();
            const next = { ...settingsRef.current, enabled: false };
            settingsRef.current = next;
            setSettings(next);
            toaster.toast({ title: "DeckHUD Lite", body: ok ? "Steam 원래 HUD 설정을 복원했습니다." : "복원할 실행 중 HUD가 없습니다." });
            await refreshStatus();
          }}>원래 Steam HUD로 복원</ButtonItem>
        </PanelSectionRow>
      </PanelSection>
    </>
  );
}

export default definePlugin(() => ({
  name: "DeckHUD Lite",
  titleView: <div className={staticClasses.Title}>DeckHUD Lite</div>,
  content: <Content />,
  icon: <FaBatteryThreeQuarters />,
  onDismount() {},
}));
