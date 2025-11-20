/// <reference types="vite/client" />

declare module '*.osm?raw' {
  const content: string
  export default content
}
