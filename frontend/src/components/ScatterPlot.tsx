import React from 'react';
import Plot from 'react-plotly.js';

// 3x3 grid region colors (editable later)
const regionColors = [
  ['#e3f2fd', '#bbdefb', '#90caf9'],
  ['#c8e6c9', '#a5d6a7', '#81c784'],
  ['#fff9c4', '#ffe082', '#ffd54f'],
];

// Draws the 3x3 grid as shapes
function getGridShapes() {
  const shapes = [];
  for (let i = 0; i < 3; i++) {
    for (let j = 0; j < 3; j++) {
      shapes.push({
        type: 'rect',
        x0: j * 100 / 3,
        x1: (j + 1) * 100 / 3,
        y0: i * 100 / 3,
        y1: (i + 1) * 100 / 3,
        xref: 'x',
        yref: 'y',
        fillcolor: regionColors[i][j],
        opacity: 0.3,
        line: { width: 1, color: '#222' },
        layer: 'below',
      });
    }
  }
  // Add bold grid lines
  for (let k = 1; k < 3; k++) {
    shapes.push({ type: 'line', x0: k * 100 / 3, x1: k * 100 / 3, y0: 0, y1: 100, line: { color: '#222', width: 2 }, xref: 'x', yref: 'y' });
    shapes.push({ type: 'line', y0: k * 100 / 3, y1: k * 100 / 3, x0: 0, x1: 100, line: { color: '#222', width: 2 }, xref: 'x', yref: 'y' });
  }
  return shapes;
}

export interface Submission {
  id: number;
  value: number;
  quality: number;
  type: string;
  category: string;
  name: string;
  location: string;
  user_id?: number;
}

interface ScatterPlotProps {
  data: Submission[];
}

const ScatterPlot: React.FC<ScatterPlotProps> = ({ data }) => {
  return (
    <Plot
      data={[
        {
          x: data.map((d) => d.quality),
          y: data.map((d) => d.value),
          text: data.map((d) => `${d.name} (${d.type}, ${d.category}, ${d.location})`),
          mode: 'markers',
          type: 'scatter',
          marker: { size: 14, color: '#003153', line: { width: 2, color: '#fff' } },
        },
      ]}
      layout={{
        width: 400,
        height: 400,
        margin: { l: 50, r: 20, t: 40, b: 50 },
        xaxis: {
          range: [0, 100],
          title: 'Quality',
          showgrid: false,
          zeroline: false,
        },
        yaxis: {
          range: [0, 100],
          title: 'Value',
          showgrid: false,
          zeroline: false,
        },
        shapes: getGridShapes(),
        plot_bgcolor: '#f7f9fa',
        paper_bgcolor: '#f7f9fa',
      }}
      config={{ displayModeBar: false }}
    />
  );
};

export default ScatterPlot;
