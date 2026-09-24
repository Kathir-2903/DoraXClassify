import { render } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AuthContext } from '../context/AuthContext';
import { ToastProvider } from '../context/ToastContext';
import { salesUser } from './fixtures';

export function renderWithProviders(ui, { route = '/', path = '*', user = salesUser } = {}) {
  const auth = { user, loading: false, login: async () => user, logout: () => {}, isAdmin: user?.role === 'admin' };
  return render(
    <MemoryRouter initialEntries={[route]}>
      <ToastProvider>
        <AuthContext.Provider value={auth}>
          <Routes>
            <Route path={path} element={ui} />
          </Routes>
        </AuthContext.Provider>
      </ToastProvider>
    </MemoryRouter>,
  );
}
