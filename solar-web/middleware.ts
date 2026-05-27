// import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

// Auth gate disabled for public-access mode. Original implementation kept
// below in case we need to re-introduce login-protected routes.
// const PROTECTED_PATHS = ["/homes", "/follows", "/following", "/alerts"];
//
// function isProtectedPath(pathname: string): boolean {
//   return PROTECTED_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));
// }

export async function middleware(_request: NextRequest) {
  return NextResponse.next();

  // --- Original auth-gating middleware (disabled) ---
  // let response = NextResponse.next({
  //   request: { headers: request.headers },
  // });
  //
  // const supabase = createServerClient(
  //   process.env.NEXT_PUBLIC_SUPABASE_URL!,
  //   process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  //   {
  //     cookies: {
  //       getAll() {
  //         return request.cookies.getAll();
  //       },
  //       setAll(cookiesToSet) {
  //         for (const { name, value, options } of cookiesToSet) {
  //           request.cookies.set(name, value);
  //           response.cookies.set(name, value, options);
  //         }
  //       },
  //     },
  //   }
  // );
  //
  // const {
  //   data: { user },
  // } = await supabase.auth.getUser();
  //
  // if (isProtectedPath(request.nextUrl.pathname) && !user) {
  //   const loginUrl = new URL("/login", request.url);
  //   loginUrl.searchParams.set("redirect", request.nextUrl.pathname);
  //   const redirectResponse = NextResponse.redirect(loginUrl);
  //   for (const cookie of response.cookies.getAll()) {
  //     redirectResponse.cookies.set(cookie);
  //   }
  //   return redirectResponse;
  // }
  //
  // if (user && request.nextUrl.pathname === "/login") {
  //   const redirectResponse = NextResponse.redirect(new URL("/homes", request.url));
  //   for (const cookie of response.cookies.getAll()) {
  //     redirectResponse.cookies.set(cookie);
  //   }
  //   return redirectResponse;
  // }
  //
  // return response;
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)",
  ],
};
