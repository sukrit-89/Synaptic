"use client";

import { useEffect, useMemo, useState } from "react";
import { Check, Pause, Play } from "lucide-react";
import { Button } from "@/components/ui/button";

const demoSteps = [
  "Mempool tx decoded",
  "Heuristics fired",
  "Anomaly fired",
  "PIS = 0.97",
  "Invariant violated",
  "Guardian pause submitted",
  "Incident report filed",
];

export function DemoConsole() {
  const [activeStep, setActiveStep] = useState(0);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    const runFromPage = () => {
      setActiveStep(0);
      setRunning(true);
      document.getElementById("demo")?.scrollIntoView({ behavior: "smooth", block: "center" });
    };

    window.addEventListener("synaptic:run-demo", runFromPage);
    return () => window.removeEventListener("synaptic:run-demo", runFromPage);
  }, []);

  useEffect(() => {
    if (!running) return;

    if (activeStep >= demoSteps.length - 1) {
      setRunning(false);
      return;
    }

    const timeout = window.setTimeout(() => {
      setActiveStep((step) => step + 1);
    }, 700);

    return () => window.clearTimeout(timeout);
  }, [activeStep, running]);

  const summary = useMemo(() => {
    if (activeStep < 3) return "Analyzing transaction";
    if (activeStep < 5) return "Exploit impact confirmed";
    if (activeStep < 6) return "Autonomous playbook active";
    return "Attack reverted, report filed";
  }, [activeStep]);

  const runDemo = () => {
    setActiveStep(0);
    setRunning(true);
  };

  return (
    <div className="w-full max-w-[520px] border border-foreground/10 bg-background/75 backdrop-blur">
      <div className="flex items-center justify-between border-b border-foreground/10 px-5 py-4">
        <div>
          <div className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Live incident demo</div>
          <div className="mt-1 text-lg font-medium">{summary}</div>
        </div>
        <span className="flex items-center gap-2 text-xs font-mono text-muted-foreground">
          <span className={`h-2 w-2 rounded-full ${running ? "bg-foreground animate-pulse" : "bg-foreground/30"}`} />
          {running ? "Running" : "Ready"}
        </span>
      </div>

      <div className="grid gap-px bg-foreground/10">
        {demoSteps.map((step, index) => {
          const complete = index <= activeStep;

          return (
            <div key={step} className="flex items-center justify-between bg-background px-5 py-3">
              <div className="flex items-center gap-3">
                <span
                  className={`flex h-6 w-6 items-center justify-center border text-xs ${
                    complete ? "border-foreground bg-foreground text-background" : "border-foreground/15 text-muted-foreground"
                  }`}
                >
                  {complete ? <Check className="h-3 w-3" /> : index + 1}
                </span>
                <span className={complete ? "text-foreground" : "text-muted-foreground"}>{step}</span>
              </div>
              {index === 3 && complete && <span className="font-mono text-xs text-foreground">97% TVL loss</span>}
            </div>
          );
        })}
      </div>

      <div className="flex flex-col gap-3 border-t border-foreground/10 p-5 sm:flex-row">
        <Button
          type="button"
          onClick={runDemo}
          className="h-12 flex-1 rounded-full bg-foreground text-background hover:bg-foreground/90"
        >
          <Play className="h-4 w-4" />
          Run demo
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={() => setRunning(false)}
          className="h-12 flex-1 rounded-full border-foreground/20 hover:bg-foreground/5"
        >
          <Pause className="h-4 w-4" />
          Pause
        </Button>
      </div>
    </div>
  );
}
