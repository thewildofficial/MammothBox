# MammothBox Frontend

React TypeScript application for the MammothBox file management system.

## Tech Stack

- **Framework**: React 18 with TypeScript
- **Build Tool**: Create React App
- **Styling**: CSS (ready for Tailwind or your preferred solution)

## Getting Started

```bash
# Navigate to the app directory
cd mammothbox

# Install dependencies (already done)
npm install

# Start development server
npm start
```

The app will open at `http://localhost:3000`

## Available Scripts

- `npm start` - Start development server
- `npm test` - Run tests
- `npm run build` - Build for production
- `npm run eject` - Eject from CRA (one-way operation)

## Project Structure

```
mammothbox/
├── public/          # Static assets
├── src/
│   ├── App.tsx     # Main application component
│   ├── App.css     # App styles
│   ├── index.tsx   # Entry point
│   └── ...
├── package.json
└── tsconfig.json
```

## Next Steps

1. Connect to backend API at `http://localhost:8000`
2. Add routing (React Router)
3. Implement file upload interface
4. Build search interface
5. Add admin dashboard
6. Style with Tailwind CSS or Material-UI
