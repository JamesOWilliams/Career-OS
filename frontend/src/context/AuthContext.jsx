import { createContext, useContext, useEffect, useState } from "react";
import client from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // null = checking
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem("co_token");
    if (!token) {
      setUser(false);
      setReady(true);
      return;
    }
    client
      .get("/auth/me")
      .then((r) => setUser(r.data))
      .catch(() => {
        localStorage.removeItem("co_token");
        setUser(false);
      })
      .finally(() => setReady(true));
  }, []);

  const login = (token, u) => {
    localStorage.setItem("co_token", token);
    setUser(u);
  };
  const logout = () => {
    localStorage.removeItem("co_token");
    setUser(false);
  };

  return (
    <AuthContext.Provider value={{ user, ready, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
