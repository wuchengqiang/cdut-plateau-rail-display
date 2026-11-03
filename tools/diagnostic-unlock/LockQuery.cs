using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Text;
public static class RailLockQuery {
 [StructLayout(LayoutKind.Sequential)] struct Unique { public uint pid; public System.Runtime.InteropServices.ComTypes.FILETIME start; }
 [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] struct Info {
  public Unique process;
  [MarshalAs(UnmanagedType.ByValTStr, SizeConst=256)] public string app;
  [MarshalAs(UnmanagedType.ByValTStr, SizeConst=64)] public string service;
  public uint type, status, session;
  [MarshalAs(UnmanagedType.Bool)] public bool restartable;
 }
 [DllImport("rstrtmgr.dll", CharSet=CharSet.Unicode)] static extern int RmStartSession(out uint session, int flags, StringBuilder key);
 [DllImport("rstrtmgr.dll", CharSet=CharSet.Unicode)] static extern int RmRegisterResources(uint session, uint count, string[] files, uint apps, IntPtr processes, uint services, IntPtr names);
 [DllImport("rstrtmgr.dll")] static extern int RmGetList(uint session, out uint needed, ref uint count, [In,Out] Info[] list, ref uint reasons);
 [DllImport("rstrtmgr.dll")] static extern int RmEndSession(uint session);
 [DllImport("shell32.dll", CharSet=CharSet.Unicode)] static extern IntPtr CommandLineToArgvW(string cmd, out int count);
 [DllImport("kernel32.dll")] static extern IntPtr LocalFree(IntPtr memory);
 public static string[] Args(string command) {
  int count; IntPtr memory=CommandLineToArgvW(command,out count);
  if(memory==IntPtr.Zero) return new string[0];
  try { var result=new string[count]; for(int i=0;i<count;i++)result[i]=Marshal.PtrToStringUni(Marshal.ReadIntPtr(memory,i*IntPtr.Size)); return result; }
  finally {LocalFree(memory);}
 }
 // Read-only Restart Manager API. Never calls RmShutdown or closes raw handles.
 public static int[] Find(string[] files) {
  if(files.Length==0)return new int[0];
  uint session; int rc=RmStartSession(out session,0,new StringBuilder(33));
  if(rc!=0)throw new Exception("RmStartSession: "+rc);
  try {
   rc=RmRegisterResources(session,(uint)files.Length,files,0,IntPtr.Zero,0,IntPtr.Zero);
   if(rc!=0)throw new Exception("RmRegisterResources: "+rc);
   for(int attempt=0;attempt<3;attempt++) {
    uint needed=0,count=0,reasons=0;rc=RmGetList(session,out needed,ref count,null,ref reasons);
    if(rc==0)return new int[0]; if(rc!=234)throw new Exception("RmGetList: "+rc);
    Info[] list=new Info[needed];count=needed;rc=RmGetList(session,out needed,ref count,list,ref reasons);
    if(rc==234)continue;if(rc!=0)throw new Exception("RmGetList: "+rc);
    var result=new List<int>();for(int i=0;i<count;i++)result.Add((int)list[i].process.pid);return result.ToArray();
   }
   throw new Exception("Restart Manager process list changed repeatedly");
  } finally {RmEndSession(session);}
 }
}
