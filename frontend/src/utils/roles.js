export const ROLES = [
  { value: 'analista', label: 'Analista' },
  { value: 'ejecutivo', label: 'Ejecutivo / decisor' },
  { value: 'admin', label: 'Administrador' },
];

export const ROLE_LABELS = Object.fromEntries(ROLES.map((role) => [role.value, role.label]));

export const roleLabel = (role) => ROLE_LABELS[role] || role || 'Sin rol';
