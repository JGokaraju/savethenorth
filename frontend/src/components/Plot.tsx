import Plotly from "plotly.js-dist-min";
import createPlotlyComponent from "react-plotly.js/factory";
import { memo } from "react";

const PlotComponent = createPlotlyComponent(Plotly);

/** Interactive Plotly figure from backend figure JSON. */
function PlotInner({ figure, height = 460 }: { figure: any; height?: number }) {
  if (!figure) return null;
  const layout = { ...figure.layout, autosize: true, height };
  return (
    <PlotComponent
      data={figure.data}
      layout={layout}
      frames={figure.frames}
      config={{ responsive: true, displaylogo: false, modeBarButtonsToRemove: ["lasso2d", "select2d"] }}
      style={{ width: "100%" }}
      useResizeHandler
    />
  );
}

export const Plot = memo(PlotInner);
