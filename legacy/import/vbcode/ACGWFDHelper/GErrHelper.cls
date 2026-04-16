VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
  Persistable = 0  'NotPersistable
  DataBindingBehavior = 0  'vbNone
  DataSourceBehavior  = 0  'vbNone
  MTSTransactionMode  = 0  'NotAnMTSObject
END
Attribute VB_Name = "GErrHelper"
Attribute VB_GlobalNameSpace = True
Attribute VB_Creatable = True
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = True
Option Explicit

Private colErrStack As Collection

Public Sub stackError(srcErr As ErrObject, srcMod As Variant, Optional srcFunc As String = vbNullString, Optional srcLine As String = vbNullString)
    If colErrStack Is Nothing Then
        Set colErrStack = New Collection
    End If
    Dim cErr As clsErrStack
    Set cErr = New clsErrStack
    cErr.errNum = srcErr.Number
    cErr.errSrc = srcErr.Source
    cErr.errDesc = srcErr.Description
    On Error Resume Next
    If IsObject(srcMod) Then
        cErr.srcMod = TypeName(srcMod)
    Else
        cErr.srcMod = srcMod
    End If
    cErr.srcMod = srcMod
    cErr.srcFunc = srcFunc
    cErr.srcLine = srcLine
    colErrStack.Add cErr
    Err.Raise srcErr.Number, srcErr.Source, srcErr.Description
End Sub

Public Function reportError(srcErr As ErrObject, srcMod As Variant, Optional srcFunc As String = vbNullString, Optional srcLine As String = vbNullString) As VbMsgBoxResult
    On Error Resume Next
    stackError srcErr, srcMod, srcFunc, srcLine
    On Error GoTo 0
    Dim strErrMsg As String
    Dim cErr As clsErrStack
    Do Until colErrStack.Count = 0
        Set cErr = colErrStack(colErrStack.Count)
        colErrStack.Remove colErrStack.Count
        strErrMsg = strErrMsg & "[" & cErr.errNum & "] "
        strErrMsg = strErrMsg & cErr.errDesc
        strErrMsg = strErrMsg & ": " & cErr.errSrc
        strErrMsg = strErrMsg & " by "
        strErrMsg = strErrMsg & cErr.srcMod
        If cErr.srcFunc > "" Then
            strErrMsg = strErrMsg & " in " & cErr.srcFunc
        End If
        If cErr.srcLine > "" Then
            strErrMsg = strErrMsg & " at " & cErr.srcLine
        End If
        strErrMsg = strErrMsg & vbCrLf
    Loop
    reportError = MsgBox("The following critical error was encountered:" & strErrMsg, vbAbortRetryIgnore Or vbCritical Or vbDefaultButton2, "Critical Error")
End Function
