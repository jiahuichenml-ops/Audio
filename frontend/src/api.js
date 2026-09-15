import axios from "axios";

export const api = axios.create({
  baseURL: "http://localhost:8003",
  timeout: 8000,
});
