import { initializeApp } from "firebase/app";
import { getAuth, GoogleAuthProvider, signInWithPopup, signOut } from "firebase/auth";

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const googleProvider = new GoogleAuthProvider();

const FRIENDLY_AUTH_ERRORS = {
  "auth/popup-closed-by-user": "Sign in popup was closed.",
  "auth/cancelled-popup-request": "Sign in popup was cancelled.",
  "auth/popup-blocked": "Sign in popup was blocked by your browser.",
};

function getFriendlyAuthError(error) {
  if (error?.code && FRIENDLY_AUTH_ERRORS[error.code]) {
    return FRIENDLY_AUTH_ERRORS[error.code];
  }
  return null;
}

export async function signInWithGoogle() {
  try {
    const result = await signInWithPopup(auth, googleProvider);
    const idToken = await result.user.getIdToken();
    const uid = result.user.uid;
    const email = result.user.email;
    const displayName = result.user.displayName;
    sessionStorage.setItem("firebaseUid", uid);
    sessionStorage.setItem("firebaseEmail", email || "");
    return { idToken, user: result.user };
  } catch (err) {
    const friendly = getFriendlyAuthError(err);
    if (friendly) {
      err._friendlyMessage = friendly;
    }
    throw err;
  }
}

export async function signOutFirebase() {
  sessionStorage.removeItem("firebaseUid");
  sessionStorage.removeItem("firebaseEmail");
  await signOut(auth);
}

export function getStoredSession() {
  return {
    uid: sessionStorage.getItem("firebaseUid") || "",
    email: sessionStorage.getItem("firebaseEmail") || "",
  };
}

export async function getIdToken() {
  if (auth.currentUser) {
    return auth.currentUser.getIdToken();
  }
  return null;
}

export { auth };
