VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
  Persistable = 0  'NotPersistable
  DataBindingBehavior = 0  'vbNone
  DataSourceBehavior  = 0  'vbNone
  MTSTransactionMode  = 0  'NotAnMTSObject
END
Attribute VB_Name = "GXMLHelper"
Attribute VB_GlobalNameSpace = True
Attribute VB_Creatable = True
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = True
'/*
' * Copyright 2004 Anite - Central Government Division
' *    http://www.anite.com/publicsector
' *
' * Licensed under the Apache License, Version 2.0 (the "License");
' * you may not use this file except in compliance with the License.
' * You may obtain a copy of the License at
' *
' *    http://www.apache.org/licenses/LICENSE-2.0
' *
' * Unless required by applicable law or agreed to in writing, software
' * distributed under the License is distributed on an "AS IS" BASIS,
' * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
' * See the License for the specific language governing permissions and
' * limitations under the License.
' */
Option Explicit

Public Function ValidatePath(Path As String) As String
    ValidatePath = basHelper.ValidatePath(Path)
End Function

Public Function XMLDoc(FirstNodeName As String) As IXMLDOMNode
    Dim oDoc As MSXML2.DOMDocument
    Dim oRoot As MSXML2.IXMLDOMNode
    Set oDoc = New MSXML2.DOMDocument
'    Set XMLDoc = XMLNode(oDoc.documentElement, FirstNodeName)
    Set oRoot = oDoc.createNode(1, FirstNodeName, "")
    oDoc.appendChild oRoot
    Set XMLDoc = oRoot
End Function

Public Function GetNodeAttr(oNode As IXMLDOMNode, Name As String, Optional DefaultValue As String = vbNullString) As String
    On Error Resume Next
    Dim strValue As String
    strValue = oNode.Attributes.getNamedItem(Name).nodeValue
    If err.Number <> 0 Then
        strValue = DefaultValue
    Else
        strValue = Replace(strValue, vbLf, vbCrLf)
    End If
    GetNodeAttr = strValue
End Function

Public Function XMLNode(oXMLNode As IXMLDOMNode, Name As String, Optional Value As String = vbNullString) As IXMLDOMNode
    Dim oRtn As MSXML2.IXMLDOMNode
    Dim oValueNode As MSXML2.IXMLDOMNode
    Dim XMLDoc As MSXML2.DOMDocument
    Set XMLDoc = oXMLNode.ownerDocument
    Set oRtn = XMLDoc.createNode(1, Name, "")
    If Len(Value) > 0 Then
        Set oValueNode = XMLDoc.createNode(3, "", "")
        oValueNode.nodeValue = Value
        oRtn.appendChild oValueNode
    End If
    oXMLNode.appendChild oRtn
    Set XMLNode = oRtn
End Function
Public Function xmlNodeDisconnected(oDoc As MSXML2.DOMDocument, Name As String, Optional Value As String = vbNullString) As IXMLDOMNode
    Dim oRtn As MSXML2.IXMLDOMNode
    Dim oValueNode As MSXML2.IXMLDOMNode
    Set oRtn = oDoc.createNode(1, Name, "")
    If Len(Value) > 0 Then
        Set oValueNode = oDoc.createNode(3, "", "")
        oValueNode.nodeValue = Value
        oRtn.appendChild oValueNode
    End If
    Set xmlNodeDisconnected = oRtn
End Function
Public Sub XMLAttr(ParentNode As IXMLDOMNode, Name As String, Value As Variant)
    Dim oAttr As MSXML2.IXMLDOMAttribute
    Set oAttr = ParentNode.ownerDocument.createAttribute(Name)
    oAttr.nodeValue = Value
    ParentNode.Attributes.setNamedItem oAttr
End Sub

'/ standard error message function
Public Function StdErrMsg(ByVal TheError As ErrObject, ByVal TheModule As String, ByVal TheSource As String) As VbMsgBoxResult
    StdErrMsg = basHelper.StdErrMsg(TheError, TheModule, TheSource)
End Function

'/ standard error raise function
Public Sub ErrRaise(ByVal TheError As ErrObject, ByVal TheModule As String, ByVal TheSource As String)
    basHelper.ErrRaise TheError, TheModule, TheSource
End Sub

'/ creates a GUID using MS API
Public Function CreateGUID() As String
    CreateGUID = basHelper.CreateGUID
End Function

Public Function IntersectBox(Left As Single, Top As Single, Width As Single, Height As Single, X As Single, Y As Single, ByRef IntersectX As Single, ByRef IntersectY As Single) As Boolean
    IntersectBox = basHelper.IntersectBox(Left, Top, Width, Height, X, Y, IntersectX, IntersectY)
End Function

Public Function IntersectBoxLine(Left As Single, Top As Single, Width As Single, Height As Single, X1 As Single, Y1 As Single, X2 As Single, Y2 As Single, ByRef IntersectX As Single, ByRef IntersectY As Single) As Boolean
    IntersectBoxLine = basHelper.IntersectBoxLine(Left, Top, Width, Height, X1, Y1, X2, Y2, IntersectX, IntersectY)
End Function

Public Function Speech(Text As String) As String
    Speech = Replace(Text, """", """""")
End Function


