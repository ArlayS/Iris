import axios from "axios";


const backendUrl = process.env.REACT_APP_BACKEND_URL;


export const api = axios.create({
  baseURL: `${backendUrl}/api`,
  withCredentials: true,
});


export const getErrorMessage = (error) =>
  error?.response?.data?.detail || "Une erreur est survenue. Réessayez.";