# React + Vite

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

## Getting Started

### Prerequisites

- [Node.js](https://nodejs.org/) (v18 or higher recommended)
- npm (included with Node.js)

### Installation

Clone the repository and install the dependencies:

```bash
npm install
```

### Available Scripts

| Command           | Description                                                       |
| ----------------- | ----------------------------------------------------------------- |
| `npm run dev`     | Starts the development server with HMR at `http://localhost:5173` |
| `npm run build`   | Builds the app for production into the `dist/` folder             |
| `npm run preview` | Serves the production build locally for previewing                |
| `npm run lint`    | Runs Oxlint to check for code issues                              |

### Running in Development

```bash
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser to see the app running.

### Building for Production

```bash
npm run build
```

To preview the production build locally:

```bash
npm run preview
```

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and Oxlint's TypeScript related rules in your project.
