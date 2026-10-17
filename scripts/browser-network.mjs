// School verification windows have their own profile and follow the OS/VPN route.
// External-provider windows retain the user's proxy configuration.
export function proxyArguments(url) {
  const {hostname} = new URL(url);
  return hostname === 'shanghaitech.edu.cn' || hostname.endsWith('.shanghaitech.edu.cn')
    ? ['--no-proxy-server'] : [];
}
