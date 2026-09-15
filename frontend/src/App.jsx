import { useState } from "react";
import RecordPanel from "./components/RecordPanel.jsx";

export default function App() {
  const [city, setCity] = useState("杭州");

  return (
    <main className="page">
      <h1>语音约碰面地点</h1>
      <p>第一版支持同一座城市内的两个人。本轮只提供本地录音，不会请求识别或找店。</p>

      <label className="city-field">
        所选城市
        <input
          value={city}
          onChange={(event) => setCity(event.target.value)}
          autoComplete="address-level2"
        />
      </label>
      <p className="meta">未口述城市时，后续提取会使用这里的城市。当前默认杭州，可修改。</p>

      <RecordPanel />
    </main>
  );
}
